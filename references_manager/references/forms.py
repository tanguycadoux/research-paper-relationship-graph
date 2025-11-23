from django import forms

from .models import Publication


class PublicationForm(forms.ModelForm):
    class Meta:
        model = Publication
        fields = ['doi', 'title', 'publication_date', 'reference_level']
        widgets = {
            'publication_date': forms.DateInput(attrs={'type': 'date'})
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Autoriser tous les champs à être vides
        for field in self.fields.values():
            field.required = False