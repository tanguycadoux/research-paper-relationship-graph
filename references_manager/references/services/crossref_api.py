import requests


def fetch_crossref_json(doi):
    """
    Retourne un JSON CrossRef pour un DOI.
    Retourne None si erreur.
    """
    if not doi:
        return None

    url = f"https://api.crossref.org/works/{doi}"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass

    return None
