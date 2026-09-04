# Cineverse

Catálogo responsivo de filmes e séries desenvolvido com HTML, CSS, JavaScript e Python. Os dados são fornecidos pela OMDb e a chave fica protegida no servidor.

## Recursos

- Catálogo paginado com centenas de títulos
- Pesquisa direta na OMDb, filtros por tipo, gênero e ano
- Detalhes com sinopse, gênero e nota IMDb
- Minha lista persistente com `localStorage`
- Skeleton loading, estados de erro e capa reserva
- Interface responsiva e acessível
- Backend Python sem dependências externas
- Testes com o `unittest` da biblioteca padrão

## Como executar

Requer Python 3.10 ou mais recente.

1. Copie `.env.example` para `.env`.
2. Coloque sua chave da [OMDb](https://www.omdbapi.com/apikey.aspx):

```env
OMDB_API_KEY=sua_chave_aqui
PORT=4173
```

3. Inicie o projeto:

```bash
python server.py
```

4. Acesse `http://localhost:4173`.

## Testes

```bash
python -m unittest -v
```

## Segurança

O arquivo `.env` está no `.gitignore` e nunca deve ser enviado ao GitHub. O navegador chama `/api/*`; somente o servidor conversa diretamente com a OMDb.

## Deploy no Render

1. Envie o projeto para um repositório GitHub.
2. No Render, crie um **Web Service** conectado ao repositório.
3. Configure `OMDB_API_KEY` como variável de ambiente secreta.
4. Use `python server.py` como comando inicial.

O arquivo `render.yaml` também permite criar o serviço como Blueprint.

## Estrutura

```text
├── index.html
├── styles.css
├── app.js
├── server.py
├── poster-placeholder.svg
├── test_server.py
└── render.yaml
```
