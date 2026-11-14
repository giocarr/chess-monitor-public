# Chess Performance Dashboard

Dashboard Streamlit per analizzare lo storico pubblico Chess.com dell'account `giocarr`.

## Avvio locale

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

La prima versione recupera gli archivi mensili dall'API pubblica di Chess.com e filtra esclusivamente le partite Rapid Rated. Non richiede password, token o chiavi API.

## Funzioni iniziali

- Volume e risultati nel tempo
- Rating associato alle partite
- Confronto Bianco/Nero
- Statistiche per apertura
- Elenco filtrabile delle partite

L'analisi approfondita delle mosse con Stockfish sarà introdotta in una fase successiva.
