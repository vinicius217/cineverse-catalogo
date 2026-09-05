# Cineverse

Catálogo de filmes e séries com pesquisa em tempo real, filtros e lista pessoal. O front-end responsivo consome uma API própria em Python, que protege a chave e centraliza as consultas ao [TMDB](https://www.themoviedb.org/) e à [OMDb](https://www.omdbapi.com/).

[![Aplicação online](https://img.shields.io/badge/abrir_aplicação-Cineverse-e5ff44?style=for-the-badge&logo=render&logoColor=111)](https://cineverse-catalogo.onrender.com)
[![Testes](https://github.com/vinicius217/cineverse-catalogo/actions/workflows/test.yml/badge.svg)](https://github.com/vinicius217/cineverse-catalogo/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)

## Sobre o projeto

O Cineverse foi criado para oferecer uma experiência simples e visual de descoberta de filmes e séries. A aplicação permite explorar títulos recentes, pesquisar por nomes em português e no idioma original, aplicar filtros por tipo e ano, consultar informações detalhadas e montar uma lista pessoal.

Além da experiência de uso, o projeto demonstra a integração entre uma interface responsiva em JavaScript e um backend em Python. O servidor atua como intermediário seguro para os provedores, mantém a chave da API fora do navegador, organiza os resultados, remove duplicidades e utiliza cache para acelerar as consultas seguintes.

O projeto também conta com testes automatizados, integração contínua pelo GitHub Actions e deploy automático no Render.

## Demonstração

**[Acessar o Cineverse online](https://cineverse-catalogo.onrender.com)**

> O serviço usa o plano gratuito do Render. O primeiro acesso após um período de inatividade pode levar alguns segundos.

## Principais recursos

- Catálogo paginado de filmes e séries
- Seleção ampliada com consultas por ano, de 2000 a 2026
- Destaques alternados com transição suave, pausa e controles manuais
- Design com título, ano e cores próprias para obras sem capa ou imagens indisponíveis
- Pesquisa na própria página, com reconhecimento de tipo, gênero e ano (ex.: `séries de 2024`)
- Filtros por tipo, gênero e ano
- Modal com sinopse em português, elenco, duração, temporadas e avaliação identificada por fonte
- Gêneros reais, ordenação por popularidade e por nota (mínimo de 100 votos, inclusive ao filtrar por ano)
- Sugestões por semelhança de títulos e fundos horizontais do TMDB
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
| Dados | TMDB (principal), OMDb (alternativa) |
| Testes | `unittest` e GitHub Actions |
| Hospedagem | Render Blueprint |

## Como funciona

```text
Navegador ── /api/catalog e /api/title ──> Servidor Python ──> TMDB / OMDb
    │                                            │
    └── interface e lista pessoal                └── cache e chave protegida
```

O navegador nunca recebe as chaves dos provedores. Todas as consultas externas passam pelo backend, que também entrega os arquivos estáticos da aplicação.

## Executando localmente

### Pré-requisitos

- Python 3.10 ou superior
- Uma chave do [TMDB](https://www.themoviedb.org/settings/api) para os recursos completos
- Opcional: [chave da OMDb](https://www.omdbapi.com/apikey.aspx) para o modo alternativo

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
TMDB_API_KEY=sua_chave_tmdb
OMDB_API_KEY=sua_chave_omdb_opcional
PORT=4173
```

Inicie o servidor:

```bash
python server.py
```

Acesse [http://localhost:4173](http://localhost:4173).

Abra pelo servidor Python: abrir `index.html` diretamente ou usar somente Live Server não disponibiliza a API.

Com `TMDB_API_KEY` (ou `TMDB_ACCESS_TOKEN`) configurada, a aplicação usa o TMDB automaticamente. A seleção reúne até 20 filmes e 20 séries populares por ano, de 2000 a 2026, com pelo menos cinco votos. A pesquisa combina essa seleção com a primeira página de resultados do TMDB; não representa toda a base. Sugestões por erros de digitação usam os nomes da seleção local. Expressões completas como `séries de drama de 2024` viram filtros, preservando os nomes de títulos reconhecidos.

Sem TMDB, a OMDb continua disponível, com seus limites: textos geralmente em inglês, capas verticais e curadoria por palavras aproximada. Configurar uma chave inválida do TMDB gera um erro recuperável, sem trocar silenciosamente os identificadores dos títulos salvos.

### Cache em disco

O filtro de ano consulta o TMDB por páginas, sem baixar o ano inteiro antes de mostrar os primeiros resultados. O botão “Carregar mais” continua a seleção, respeitando tipo, gênero e ordenação. Anos que ultrapassam o limite de páginas do provedor são divididos em intervalos de datas. Títulos sem votos aparecem nas demais ordenações; “Mais bem avaliados” exige pelo menos 100 votos e ordena pela maior nota.

Respostas dos provedores e a seleção ficam em SQLite, em `.cache/catalog.sqlite3`, fora do Git e sem acesso público. O cache sobrevive a reinícios do processo enquanto o disco permanece disponível. O catálogo TMDB expira em 24 horas; respostas de metadados, em sete dias; buscas, em uma hora. Dados anteriores podem ser usados em caso de falha do provedor.

O [Render gratuito](https://render.com/docs/free) tem disco efêmero: novos deploys e recriações da instância podem apagar o cache. Para persistência entre deploys, configure `CATALOG_CACHE_PATH` em um volume persistente, por exemplo `/var/data/catalog.sqlite3`. Nenhum plano pago é contratado por esta configuração.

## API

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/health` | Verifica provedor, versão e commit publicado |
| `GET` | `/api/catalog` | Lista, pesquisa, filtra e pagina os títulos |
| `GET` | `/api/title/:id` | Retorna detalhes por IMDb ID ou `tmdb-movie-ID` / `tmdb-tv-ID` |

Exemplo de pesquisa:

```text
/api/catalog?q=Matrix&type=Filme&page=1&pageSize=24
```

## Testes

```bash
python -m unittest -v
node test_app.js
```

O teste JavaScript usa Node.js e verifica o design sem capa, a recuperação de imagens e os controles do carrossel. Os testes Python e JavaScript são executados automaticamente pelo GitHub Actions a cada `push` e `pull request`.

## Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fvinicius217%2Fcineverse-catalogo)

O [`render.yaml`](render.yaml) cria o serviço web e utiliza `python server.py` como comando de inicialização. Durante a configuração, informe `TMDB_API_KEY` como variável secreta (e `OMDB_API_KEY` se desejar a alternativa). Depois de salvar as variáveis no painel do Render, reinicie/publique o serviço. O endpoint `/api/health` deve informar `provider: TMDB`.

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
- As chaves dos provedores existem apenas no servidor.
- Arquivos internos como `.env`, fontes Python e configuração do Render não são servidos publicamente.

---

Desenvolvido por [Vinicius Madalossi](https://github.com/vinicius217).
