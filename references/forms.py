from django import forms

from .models import Author, Publication
from .services.doi import is_valid_doi, normalize_doi


class PublicationForm(forms.ModelForm):
    class Meta:
        model = Publication
        fields = ["doi", "title", "publication_date"]
        widgets = {"publication_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Every field is optional: a publication may be created from partial data.
        for field in self.fields.values():
            field.required = False


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


class AuthorMergeConfirmForm(forms.Form):
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    orcid = forms.CharField(required=False)


class IdentifyReferenceForm(forms.Form):
    METHOD_DOI = "doi"
    METHOD_NONE = "none"

    method = forms.ChoiceField(
        label="Identifier par",
        choices=[(METHOD_DOI, "DOI"), (METHOD_NONE, "Sans identifiant")],
        widget=forms.RadioSelect,
        initial=METHOD_DOI,
    )
    doi = forms.CharField(label="DOI", required=False)
    title = forms.CharField(label="Titre", required=False)
    year = forms.IntegerField(label="Année", required=False, min_value=1000, max_value=2100)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("method") == self.METHOD_DOI:
            self.clean_identifier_doi(cleaned)
        elif not cleaned.get("title"):
            self.add_error("title", "Le titre est obligatoire sans identifiant.")
        return cleaned

    def clean_identifier_doi(self, cleaned):
        doi = normalize_doi(cleaned.get("doi", ""))
        if not is_valid_doi(doi):
            self.add_error("doi", "Veuillez entrer un DOI valide (de la forme 10.xxxx/…).")
        cleaned["doi"] = doi
