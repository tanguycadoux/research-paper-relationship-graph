from django import forms
from django.urls import reverse
from django.utils.html import format_html

from .models import Author, Publication
from .services.doi import is_valid_doi, normalize_doi
from .services.isbn import is_valid_isbn, normalize_isbn
from .services.orcid import normalize_orcid


class PublicationForm(forms.ModelForm):
    # Longer than the stored ISBN-13: hyphens and ISBN-10 are accepted, then normalized.
    isbn = forms.CharField(label="ISBN", max_length=20, required=False)

    class Meta:
        model = Publication
        fields = ["doi", "isbn", "title", "publication_date"]
        labels = {"doi": "DOI", "title": "Titre", "publication_date": "Date de publication"}
        widgets = {
            # <input type="date"> needs ISO dates, whatever the locale.
            "publication_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Every field is optional: a publication may be created from partial data.
        for field in self.fields.values():
            field.required = False

    def clean(self):
        cleaned_data = super().clean()
        if not any(cleaned_data.get(name) for name in ("doi", "isbn", "title")):
            raise forms.ValidationError("Indiquez au moins un DOI, un ISBN ou un titre.")
        return cleaned_data

    def clean_doi(self):
        # Normalized here, not only in Publication.save(): the uniqueness check
        # must compare normalized values (#145).
        doi = normalize_doi(self.cleaned_data["doi"])
        if doi and not is_valid_doi(doi):
            raise forms.ValidationError("Veuillez entrer un DOI valide (de la forme 10.xxxx/…).")
        self.check_not_taken("doi", doi, "Une publication avec ce DOI existe déjà")
        return doi

    def clean_isbn(self):
        isbn = normalize_isbn(self.cleaned_data["isbn"])
        if isbn and not is_valid_isbn(isbn):
            raise forms.ValidationError("Veuillez entrer un ISBN-10 ou ISBN-13 valide.")
        self.check_not_taken("isbn", isbn, "Une publication avec cet ISBN existe déjà")
        return isbn

    def check_not_taken(self, field, value, message):
        """Refuse an identifier held by another publication, with a link to it."""
        if not value:
            return
        existing = Publication.objects.filter(**{field: value}).exclude(pk=self.instance.pk)
        if other := existing.first():
            url = reverse("publication_detail", args=[other.pk])
            raise forms.ValidationError(
                format_html('{} : <a href="{}">{}</a>.', message, url, other)
            )


class AuthorChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, author):
        if author.orcid:
            return f"{author} (ORCID : {author.orcid})"
        return str(author)


class AuthorMergeSelectForm(forms.Form):
    authors = AuthorChoiceField(
        queryset=Author.objects.order_by("last_name", "first_name"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ["first_name", "last_name", "orcid"]
        labels = {"first_name": "Prénom", "last_name": "Nom", "orcid": "ORCID"}

    def clean_orcid(self):
        return normalize_orcid(self.cleaned_data["orcid"])


class AuthorMergeConfirmForm(forms.Form):
    """
    For each field, a choice among the values of the merged authors, or another
    value typed by the user. Two different ORCIDs require an explicit confirmation.
    """

    OTHER = "__other__"
    LABELS = {"first_name": "Prénom", "last_name": "Nom", "orcid": "ORCID"}

    def __init__(self, *args, candidates, orcid_conflict=False, **kwargs):
        super().__init__(*args, **kwargs)
        for field, label in self.LABELS.items():
            self.fields[field] = forms.ChoiceField(
                label=label,
                choices=self.choices(field, candidates[field]),
                widget=forms.RadioSelect,
                required=field != "orcid",  # "Aucun" (no ORCID) is a valid choice
            )
            self.fields[f"{field}_other"] = forms.CharField(label="Autre valeur", required=False)
        if orcid_conflict:
            self.fields["confirm_orcid_conflict"] = forms.BooleanField(
                label="Je confirme : ces ORCID différents désignent bien la même personne.",
                required=True,
            )

    def choices(self, field, values):
        choices = [(value, value) for value in values]
        if field == "orcid":
            choices.append(("", "Aucun"))
        return [*choices, (self.OTHER, "Autre valeur :")]

    def field_groups(self):
        """(choice, other value) bound fields of each merged field, for the template."""
        return [(self[field], self[f"{field}_other"]) for field in self.LABELS]

    def clean(self):
        cleaned = super().clean()
        for field in self.LABELS:
            if cleaned.get(field) == self.OTHER:
                cleaned[field] = cleaned.get(f"{field}_other", "").strip()
        if "orcid" in cleaned:
            cleaned["orcid"] = normalize_orcid(cleaned["orcid"])
        return cleaned


class IdentifyReferenceForm(forms.Form):
    METHOD_DOI = "doi"
    METHOD_ISBN = "isbn"
    METHOD_NONE = "none"

    method = forms.ChoiceField(
        label="Identifier par",
        choices=[(METHOD_DOI, "DOI"), (METHOD_ISBN, "ISBN"), (METHOD_NONE, "Sans identifiant")],
        widget=forms.RadioSelect,
        initial=METHOD_DOI,
    )
    doi = forms.CharField(label="DOI", required=False)
    isbn = forms.CharField(label="ISBN", required=False)
    title = forms.CharField(label="Titre", required=False)
    year = forms.IntegerField(label="Année", required=False, min_value=1000, max_value=2100)

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("method")
        if method == self.METHOD_DOI:
            self.clean_identifier_doi(cleaned)
        elif method == self.METHOD_ISBN:
            self.clean_identifier_isbn(cleaned)
        elif not cleaned.get("title"):
            self.add_error("title", "Le titre est obligatoire sans identifiant.")
        return cleaned

    def clean_identifier_doi(self, cleaned):
        doi = normalize_doi(cleaned.get("doi", ""))
        if not is_valid_doi(doi):
            self.add_error("doi", "Veuillez entrer un DOI valide (de la forme 10.xxxx/…).")
        cleaned["doi"] = doi

    def clean_identifier_isbn(self, cleaned):
        isbn = normalize_isbn(cleaned.get("isbn", ""))
        if not is_valid_isbn(isbn):
            self.add_error("isbn", "Veuillez entrer un ISBN-10 ou ISBN-13 valide.")
        cleaned["isbn"] = isbn


class MergePublicationForm(forms.Form):
    target = forms.CharField(
        label="DOI, ISBN ou lien d'une publication de l'application", max_length=500
    )
    confirm = forms.BooleanField(required=False, widget=forms.HiddenInput)
