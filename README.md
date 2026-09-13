 # Encurtalink

Encurtador de links simples, feito com Python, FastAPI e Uvicorn. A página web e a API são servidas pelo mesmo processo.

## Rodando localmente

Requer Python 3.10 ou superior.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload
```

Abra `http://localhost:8000` no navegador.

## API

`POST /api/links`

```json
{ "url": "https://github.com" }
```

Retorna o código criado e a URL curta. A rota `GET /{codigo}` redireciona para o destino original e registra o clique.
