# Cineverse

Catálogo de filmes e séries com pesquisa, filtros, destaques e lista pessoal. O backend usa Python e sua biblioteca padrão; a interface usa HTML, CSS e JavaScript.

[Abrir aplicação](https://cineverse-catalogo.onrender.com) · [GitHub Actions](https://github.com/vinicius217/cineverse-catalogo/actions/workflows/test.yml)

## Executar localmente

Você precisa de **Python 3.10 ou superior** e de uma credencial do TMDB ou da OMDb. Não é necessário instalar pacotes com `pip` ou `npm` para executar a aplicação.

Clone o repositório e entre na pasta:

```powershell
git clone https://github.com/vinicius217/cineverse-catalogo.git
cd cineverse-catalogo
```

Crie um arquivo `.env` na raiz, ao lado de `README.md`, com sua chave:

```env
TMDB_API_KEY=sua_chave_tmdb
PORT=4173
```

Se o `.env` já existir, apenas confira as variáveis. O `.env.example`, quando disponível localmente, pode servir de referência; ele não é versionado.

Inicie o servidor **na raiz do projeto**:

```powershell
python -m backend.server
```

Abra **[http://localhost:4173](http://localhost:4173)**. Para encerrar, pressione `Ctrl+C` no terminal.

No Windows, se `python` não for reconhecido, tente `py -m backend.server`. Abra a aplicação pelo servidor: abrir `frontend/index.html` diretamente ou usar apenas Live Server não disponibiliza a API.

### Variáveis de ambiente

| Variável | Uso |
| --- | --- |
| `TMDB_API_KEY` | Chave do TMDB, provedor principal |
| `TMDB_ACCESS_TOKEN` | Alternativa à chave do TMDB; tem prioridade quando ambos estão definidos |
| `OMDB_API_KEY` | Chave para usar OMDb quando não há credencial do TMDB |
| `PORT` | Porta HTTP; padrão `4173` |
| `CATALOG_CACHE_PATH` | Caminho do cache SQLite; padrão `.cache/catalog.sqlite3` |

Configure ao menos um provedor. Para usar somente OMDb, deixe as variáveis do TMDB ausentes ou vazias e preencha `OMDB_API_KEY`. Uma credencial inválida do TMDB não aciona a troca automática para OMDb. Reinicie o servidor após alterar o `.env`.

## Funcionalidades

- Pesquisa sem recarregar a página, com filtros por tipo, gênero e ano.
- Catálogo paginado e botão “Carregar mais”.
- Destaques com carrossel, pausa e controles manuais.
- Modal com sinopse, elenco, duração e avaliação.
- Lista pessoal salva no navegador, sem cadastro.
- Layout responsivo, imagens alternativas e estados de carregamento e erro.
- Cache de dados no servidor.

Com TMDB, a aplicação oferece textos em português quando disponíveis, gêneros do provedor, sugestões de títulos, busca por semelhança e ordenação por popularidade ou avaliação. A seleção inicial cobre 2000 a 2026; a pesquisa também consulta o provedor, mas não percorre toda a base. A ordenação por avaliação exige pelo menos 100 votos.

A OMDb oferece o modo alternativo, com textos geralmente em inglês e gêneros aproximados na seleção inicial. Os recursos disponíveis variam conforme o provedor.

## Organização

```text
.
├── backend/
│   ├── __init__.py
│   ├── config.py          # Caminhos, anos e leitura do .env
│   ├── library.py         # TMDB, pesquisa e cache SQLite compartilhado
│   ├── omdb.py            # Catálogo, pesquisa e detalhes da OMDb
│   ├── presentation.py    # Geração dos fragmentos HTML
│   └── server.py          # Servidor HTTP, rotas e arquivos públicos
├── frontend/
│   ├── app.js             # Interações e chamadas à API
│   ├── index.html         # Estrutura da página
│   ├── poster-placeholder.svg
│   └── styles.css         # Estilos e responsividade
├── tests/
│   ├── __init__.py
│   ├── test_app.js
│   ├── test_library.py
│   ├── test_omdb.py
│   ├── test_presentation.py
│   └── test_server.py
├── .github/workflows/test.yml
├── .gitignore
├── README.md
└── render.yaml
```

O Python consulta os provedores e gera o HTML dos cards, capas, sugestões e detalhes. O JavaScript insere esse conteúdo e controla pesquisa, paginação, carrossel, modal e lista pessoal. A página precisa de JavaScript para carregar o catálogo.

As chamadas às APIs de dados passam pelo backend; o navegador carrega imagens dos provedores diretamente. As credenciais ficam no servidor. A lista pessoal usa `localStorage` e não é sincronizada entre dispositivos.

O cache fica em `.cache/catalog.sqlite3` e pode ser reutilizado após reiniciar o processo, desde que o arquivo permaneça no disco. `.env` e `.cache/` são ignorados pelo Git. O servidor entrega apenas os arquivos públicos permitidos de `frontend/`.

## API

| Método | Rota | Resposta |
| --- | --- | --- |
| `GET` | `/api/health` | Estado da configuração, provedor, versão e commit |
| `GET` | `/api/catalog` | Títulos, paginação e fragmentos HTML |
| `GET` | `/api/title/:id` | Dados e HTML de um título |

Exemplo:

```text
/api/catalog?q=Matrix&type=Filme&page=1&pageSize=24
```

O catálogo aceita `q`, `type`, `genre`, `year`, `order`, `page` e `pageSize`. Os identificadores de títulos são IDs IMDb ou valores como `tmdb-movie-123` e `tmdb-tv-456`.

## Testes

Execute na raiz do projeto:

```powershell
python -m unittest discover -v
node --check frontend/app.js
node tests/test_app.js
```

Node.js é necessário apenas para as verificações JavaScript. Os testes Python cobrem provedores, pesquisa, paginação, cache, HTML e rotas HTTP. Os testes JavaScript verificam chamadas à API, recuperação de imagens e comportamento do carrossel. O GitHub Actions executa as verificações em pushes e pull requests.

## Deploy no Render

O [render.yaml](render.yaml) define um serviço Python com:

- **Start Command:** `python -m backend.server`
- **Health Check Path:** `/api/health`

Configure as credenciais nas variáveis de ambiente do serviço. O Blueprint solicita `OMDB_API_KEY`; para usar TMDB, adicione `TMDB_API_KEY` ou `TMDB_ACCESS_TOKEN` no painel do Render. O `.env` local não é enviado ao repositório.

Com deploy automático habilitado para `main`, um push nessa branch inicia a publicação. Em um serviço criado manualmente, confira o Start Command após mudanças na estrutura de pastas. A resposta de `/api/health` informa o commit em execução para conferir a versão publicada.

O cache pode ser perdido quando o disco da hospedagem é recriado. Se houver um volume persistente configurado, aponte `CATALOG_CACHE_PATH` para esse volume.

---

Desenvolvido por [Vinicius Madalossi](https://github.com/vinicius217).
