# Cineverse

Catálogo de filmes e séries com pesquisa em tempo real, filtros e lista pessoal. O front-end responsivo consome uma API própria em Python, que protege a chave e centraliza as consultas à [OMDb](https://www.omdbapi.com/).

[![Aplicação online](https://img.shields.io/badge/abrir_aplicação-Cineverse-e5ff44?style=for-the-badge&logo=render&logoColor=111)](https://cineverse-catalogo.onrender.com)
[![Testes](https://github.com/vinicius217/cineverse-catalogo/actions/workflows/test.yml/badge.svg)](https://github.com/vinicius217/cineverse-catalogo/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)

## Sobre o projeto

O Cineverse foi criado para oferecer uma experiência simples e visual de descoberta de filmes e séries. A aplicação permite explorar títulos recentes, pesquisar diretamente na base da OMDb, aplicar filtros por tipo e ano, consultar informações detalhadas e montar uma lista pessoal.

Além da experiência de uso, o projeto demonstra a integração entre uma interface responsiva em JavaScript e um backend em Python. O servidor atua como intermediário seguro para a OMDb, mantém a chave da API fora do navegador, organiza os resultados, remove duplicidades e utiliza cache para acelerar as consultas seguintes.

O projeto também conta com testes automatizados, integração contínua pelo GitHub Actions e deploy automático no Render.

## Demonstração

**[Acessar o Cineverse online](https://cineverse-catalogo.onrender.com)**

> O serviço usa o plano gratuito do Render. O primeiro acesso após um período de inatividade pode levar alguns segundos.

## Principais recursos

- Catálogo paginado de filmes e séries
- Pesquisa direta na OMDb por título
- Filtros por tipo, gênero e ano
- Modal com sinopse, gênero, ano e avaliação IMDb
- Lista pessoal persistida no navegador com `localStorage`
- Skeleton loading, estados de erro e imagem reserva
- Layout responsivo para desktop, tablet e celular
- Navegação por teclado e atributos de acessibilidade
- Cache do catálogo e dos detalhes no servidor
- Backend Python sem dependências externas

## Tecnologias

| Camada | Tecnologias |
| --- | --- |
| Interface | HTML5, CSS3 e JavaScript |
| Backend | Python e biblioteca padrão (`http.server`, `urllib`) |
| Dados | OMDb API |
| Testes | `unittest` e GitHub Actions |
| Hospedagem | Render Blueprint |

## Como funciona

```text
Navegador ── /api/catalog e /api/title ──> Servidor Python ──> OMDb API
    │                                            │
    └── interface e lista pessoal                └── cache e chave protegida
```

O navegador nunca recebe a chave da OMDb. Todas as consultas externas passam pelo backend, que também entrega os arquivos estáticos da aplicação.

## Executando localmente

### Pré-requisitos

- Python 3.10 ou superior
- Uma [chave gratuita da OMDb](https://www.omdbapi.com/apikey.aspx)

### Instalação

```bash
git clone https://github.com/vinicius217/cineverse-catalogo.git
cd cineverse-catalogo
cp .env.example .env
```

No Windows PowerShell, substitua o último comando por:

```powershell
Copy-Item .env.example .env
```

Preencha o `.env`:

```env
OMDB_API_KEY=sua_chave_aqui
PORT=4173
```

Inicie o servidor:

```bash
python server.py
```

Acesse [http://localhost:4173](http://localhost:4173).

## API

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/health` | Verifica o servidor e a configuração da OMDb |
| `GET` | `/api/catalog` | Lista, pesquisa, filtra e pagina os títulos |
| `GET` | `/api/title/:id` | Retorna os detalhes pelo IMDb ID |

Exemplo de pesquisa:

```text
/api/catalog?q=Matrix&type=Filme&page=1&pageSize=24
```

## Testes

```bash
python -m unittest -v
```

Os mesmos testes são executados automaticamente pelo GitHub Actions a cada `push` e `pull request`.

## Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fvinicius217%2Fcineverse-catalogo)

O [`render.yaml`](render.yaml) cria o serviço web e utiliza `python server.py` como comando de inicialização. Durante a configuração, informe `OMDB_API_KEY` como variável secreta.

## Estrutura do projeto

```text
.
├── .github/workflows/test.yml  # Integração contínua
├── app.js                      # Estado e interações da interface
├── index.html                  # Estrutura da aplicação
├── poster-placeholder.svg      # Imagem reserva
├── render.yaml                 # Infraestrutura do Render
├── server.py                   # API, cache e servidor estático
├── styles.css                  # Layout e responsividade
└── test_server.py              # Testes automatizados
```

## Segurança

- O `.env` é ignorado pelo Git e não deve ser versionado.
- A chave da OMDb existe apenas no servidor.
- Arquivos internos como `.env`, fontes Python e configuração do Render não são servidos publicamente.

---

Desenvolvido por [Vinicius Madalossi](https://github.com/vinicius217).
