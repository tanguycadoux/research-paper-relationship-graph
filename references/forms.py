from django import forms

from .models import Author, Publication


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
