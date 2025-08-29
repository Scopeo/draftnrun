import pandas as pd

COGITERRA_URL_COLUMN_NAME = "url"
COGITERRA_ORGANIZATION_ID = "01b6554c-4884-409f-a0e1-22e394bee111"
URL_BEGINNING = "https://www.actu-environnement.com/ae/news/"


def create_cogiterra_url(db_row) -> None:
    nom_fichier = db_row.get("nom_fichier")
    id_news = db_row.get("id_news")
    if pd.notna(nom_fichier) and pd.notna(id_news):
        return f"{URL_BEGINNING}{nom_fichier}{id_news}.php4"
    if pd.notna(id_news):
        return f"{URL_BEGINNING}{id_news}.php4"
    return None
