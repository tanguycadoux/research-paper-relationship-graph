from django import forms

from .models import Publication, Author


class PublicationForm(forms.ModelForm):
    class Meta:
        model = Publication
        fields = ['doi', 'title', 'publication_date']
        widgets = {
            'publication_date': forms.DateInput(attrs={'type': 'date'})
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Autoriser tous les champs à être vides
        for field in self.fields.values():
            field.required = False

class AuthorMergeSelectForm(forms.Form):
    authors = forms.ModelMultipleChoiceField(
        queryset=Author.objects.order_by("last_name", "first_name"),
        widget=forms.CheckboxSelectMultiple,
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for i, sub in enumerate(self.fields['authors'].widget.subwidgets(
            name='authors',
            value=self['authors'].value()
        )):
            author = self.fields['authors'].queryset[i]
            print(author)
            sub.author_obj = author

class AuthorMergeConfirmForm(forms.Form):
    first_name = forms.CharField(required=False)
    last_name  = forms.CharField(required=False)
    orcid      = forms.CharField(required=False)
