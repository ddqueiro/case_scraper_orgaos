# 📊 Scraper de Órgãos Regulatórios Internacionais

Este projeto realiza a coleta automatizada do **comunicado mais recente** publicado por três grandes órgãos regulatórios internacionais:

- 🇭🇰 SFC – Securities and Futures Commission (Hong Kong)
- 🇸🇬 MAS – Monetary Authority of Singapore
- 🇺🇸 CFTC – Commodity Futures Trading Commission (EUA)

O sistema combina **APIs oficiais + scraping HTML resiliente**, garantindo extração confiável e padronizada.

---

## Objetivo

Extrair automaticamente o item mais recente de cada órgão regulador, contendo:

- Título da publicação
- Data de publicação
- Link do artigo
- Conteúdo principal (resumido)
- Status da execução

---

## Arquitetura

- SFC → API oficial + validação incremental
- MAS → API Solr (busca estruturada)
- CFTC → scraping HTML da tabela pública

---

## Estrutura do projeto

.
├── scraper.py
├── dados_regulatorios.json
└── README.md

---

## Tecnologias utilizadas

- Python >= 3.10
- requests
- BeautifulSoup4
- JSON
- APIs públicas

---

## Instalação

pip install requests beautifulsoup4

---

## Execução

python scraper.py

---

### Exemplo de saída

```json

[
  {
    "url_origem": "https://www.sfc.hk/en/News-and-announcements/News",
    "url_artigo": "https://apps.sfc.hk/edistributionWeb/gateway/EN/news-and-announcements/news/doc?refNo=26PR100",
    "titulo": "Example Regulatory Announcement",
    "data_publicacao": "25 Jun 2026",
    "conteudo_principal": "Resumo do conteúdo da publicação...",
    "status": "sucesso",
    "mensagem_erro": null
  }
]
```

## Tratamento de erros

- Timeout
- HTTP errors
- Fallback de scraping
- Logs de erro

---

## Características

- Coleta automática do item mais recente
- Estrutura padronizada
- Uso de APIs oficiais quando possível

---

## 👤 Autor

Projeto de automação de dados regulatórios criado por Dannyelly Queiroz.