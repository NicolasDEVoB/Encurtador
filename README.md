 # Encurtaí

Encurtador de links simples, feito com Python, FastAPI e Uvicorn. A página web e a API são servidas pelo mesmo processo.

## Rodando localmente

Requer Python 3.10 ou superior.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload
```

Abra `http://localhost:8000` no navegador. Os links criados ficam em `data/links.sqlite3`.

## Publicando

O projeto pode ser publicado em Render, Railway, Fly.io ou qualquer serviço que execute Python:

1. Conecte este repositório ao serviço.
2. Use `python3 -m pip install -r requirements.txt` como comando de instalação.
3. Use `python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT` como comando de inicialização.
4. Configure `PUBLIC_URL` com a URL pública do serviço, por exemplo `https://encurtai.onrender.com`.

O armazenamento atual usa SQLite. Para não perder links quando a plataforma recriar a instância, habilite um disco persistente ou substitua o arquivo por PostgreSQL ou Redis.

## API

`POST /api/links`

```json
{ "url": "https://github.com" }
```

Retorna o código criado e a URL curta. A rota `GET /{codigo}` redireciona para o destino original e registra o clique.
