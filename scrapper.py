"""
Scraper de órgãos regulatórios internacionais.

Extrai o item MAIS RECENTE da primeira página de cada órgão:
  - SFC (Hong Kong) via API oficial
  - MAS (Singapura) via API de busca Solr
  - CFTC (EUA) via primeira linha da tabela HTML

Salva os resultados em dados_regulatorios.json.
"""

import json
import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

CABECALHOS_HTTP = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

URLS_REGULADORES = [
    "https://www.sfc.hk/en/News-and-announcements/News",
    "https://www.mas.gov.sg/news/media-releases",
    "https://www.cftc.gov/PressRoom/PressReleases",
]

ARQUIVO_SAIDA = "dados_regulatorios.json"
TIMEOUT_SEGUNDOS = 15
TAMANHO_CONTEUDO = 300

SFC_API_BASE = "https://apps.sfc.hk/edistributionWeb/api/news"
SFC_URL_ARTIGO = (
    "https://apps.sfc.hk/edistributionWeb/gateway/EN/news-and-announcements/news/doc?refNo={ref_no}"
)
MAS_API_BUSCA = (
    "https://www.mas.gov.sg/api/v1/search"
    "?json.nl=map&q=*:*&start=0&rows=1"
    "&sort=mas_date_tdt%20desc"
    "&fq=mas_contenttype_s:%22Media%20Releases%22"
)

# Textos de interface que devem ser removidos do conteúdo extraído
RUÍDOS_UI = re.compile(
    r"(Decrease font size|Increase font size|Print this page|"
    r"Media Releases|Published Date:|Home News|Share|Compartilhe|"
    r"Release Number\s+\d+-\d+|"
    r"You need to enable JavaScript to run this app\.?)",
    re.I,
)


def extrair_data_texto(texto: str) -> str | None:
    """Busca uma data no texto (formatos em inglês e DD/MM/AAAA)."""
    padroes = [
        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2}\b",
        r"\b[A-Za-z]{3,9}\s+\d{1,2},\s+20\d{2}\b",
        r"\b\d{2}/\d{2}/\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]
    for padrao in padroes:
        correspondencia = re.search(padrao, texto)
        if correspondencia:
            return correspondencia.group(0)
    return None


def formatar_data_iso(valor: str) -> str:
    """Normaliza datas ISO (2026-06-25T21:30:00Z) para formato legível."""
    valor = valor.strip()
    try:
        if "T" in valor:
            dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
            return dt.strftime("%d %b %Y")
    except ValueError:
        pass
    return valor


def limpar_texto(texto: str) -> str:
    """Remove ruídos de interface e normaliza espaços em branco."""
    texto = unescape(texto)
    texto = RUÍDOS_UI.sub(" ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def extrair_conteudo_principal(soup: BeautifulSoup, limite: int = TAMANHO_CONTEUDO) -> str:
    """Extrai o texto principal da página, ignorando navegação e scripts."""
    for lixo in soup(["script", "style", "nav", "footer", "header", "form"]):
        lixo.decompose()

    corpo = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"content|article|body|field--name-body", re.I))
        or soup.find("body")
    )

    if not corpo:
        return "Não foi possível extrair o conteúdo principal."

    texto_limpo = limpar_texto(corpo.get_text(" "))

    if not texto_limpo or "enable JavaScript" in texto_limpo:
        return "Não foi possível extrair o conteúdo principal."

    if len(texto_limpo) > limite:
        return texto_limpo[:limite] + "..."

    return texto_limpo


def buscar_html(url: str) -> str | None:
    """Requisição HTTP com tratamento de erros de rede."""
    try:
        resposta = requests.get(url, headers=CABECALHOS_HTTP, timeout=TIMEOUT_SEGUNDOS)
        resposta.raise_for_status()
        return resposta.text
    except requests.exceptions.Timeout:
        print(f"[ERRO] Timeout ao acessar: {url}")
    except requests.exceptions.ConnectionError:
        print(f"[ERRO] Falha de conexão com: {url}")
    except requests.exceptions.HTTPError as erro:
        codigo = erro.response.status_code if erro.response else "?"
        print(f"[ERRO] HTTP {codigo} ao acessar: {url}")
    except requests.exceptions.RequestException as erro:
        print(f"[ERRO] Requisição falhou para {url}: {erro}")
    return None


def processar_artigo_html(link_artigo: str, titulo_fallback: str, data_fallback: str) -> dict:
    """Acessa a página interna do artigo e extrai título, data e resumo."""
    print(f"  -> Acessando artigo: {link_artigo}")

    resultado = {
        "titulo": titulo_fallback,
        "data_publicacao": data_fallback,
        "conteudo_principal": "Não foi possível extrair o conteúdo principal.",
    }

    html = buscar_html(link_artigo)
    if html is None:
        return resultado

    soup = BeautifulSoup(html, "html.parser")

    # Título completo: prioriza <h1> descritivo, depois <title>
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        titulo_h1 = h1.get_text(strip=True)
        # CFTC usa h1 genérico ("Release Number 9262-26"); mantém o da listagem
        if not re.match(r"^Release Number\s+\d", titulo_h1, re.I):
            resultado["titulo"] = titulo_h1
    if resultado["titulo"] == titulo_fallback:
        tag_titulo = soup.find("title")
        if tag_titulo and tag_titulo.get_text(strip=True):
            titulo_pagina = tag_titulo.get_text(strip=True)
            if not re.match(r"^Release Number\s+\d", titulo_pagina, re.I):
                resultado["titulo"] = titulo_pagina

    # Data: meta tags ou padrão no texto
    for tag, attrs in [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"property": "og:published_time"}),
        ("meta", {"name": "date"}),
    ]:
        elemento = soup.find(tag, attrs=attrs)
        if elemento and elemento.get("content"):
            data = extrair_data_texto(elemento["content"])
            if data:
                resultado["data_publicacao"] = data
                break

    if resultado["data_publicacao"] == "Não identificada":
        data_texto = extrair_data_texto(soup.get_text(" "))
        if data_texto:
            resultado["data_publicacao"] = data_texto

    resultado["conteudo_principal"] = extrair_conteudo_principal(soup)
    return resultado


# ---------------------------------------------------------------------------
# Extração por órgão — sempre o item MAIS RECENTE (primeira página)
# ---------------------------------------------------------------------------


def obter_sfc_mais_recente(cabecalhos_api: dict) -> dict:
    """
    Obtém o press release mais recente da SFC.

    A API de busca pode não listar o item mais novo imediatamente (ex: 26PR100).
    Por isso, após a busca ordenada por data, verifica refs posteriores via
    /api/news/content até encontrar o último existente.
    """
    resposta_busca = requests.post(
        f"{SFC_API_BASE}/search",
        headers=cabecalhos_api,
        json={
            "pageNo": 1,
            "pageSize": 10,
            "lang": "EN",
            "sortBy": "issueDate",
            "sortOrder": "desc",
        },
        timeout=TIMEOUT_SEGUNDOS,
    )
    resposta_busca.raise_for_status()
    itens = resposta_busca.json()["items"]
    melhor = max(itens, key=lambda item: item["issueDate"])

    correspondencia = re.match(r"(\d+)PR(\d+)", melhor["newsRefNo"])
    if not correspondencia:
        return melhor

    prefixo, numero = correspondencia.groups()
    numero_atual = int(numero)

    # Verifica refs posteriores não indexados na busca (ex: 26PR100 após 26PR99)
    while True:
        proximo_ref = f"{prefixo}PR{numero_atual + 1}"
        resposta = requests.get(
            f"{SFC_API_BASE}/content",
            headers=cabecalhos_api,
            params={"refNo": proximo_ref, "lang": "EN"},
            timeout=TIMEOUT_SEGUNDOS,
        )
        if resposta.status_code != 200:
            break

        dados = resposta.json()
        melhor = {
            "newsRefNo": proximo_ref,
            "title": dados.get("title", ""),
            "issueDate": dados.get("issueDate", ""),
        }
        numero_atual += 1

    return melhor


def processar_sfc(url_origem: str) -> dict:
    """
    SFC usa SPA (JavaScript). Os dados vêm da API oficial e o link público
    do artigo segue o formato: .../news/doc?refNo=26PR100
    """
    registro = {
        "url_origem": url_origem,
        "url_artigo": None,
        "titulo": None,
        "data_publicacao": "Não identificada",
        "conteudo_principal": None,
        "status": "erro",
        "mensagem_erro": None,
    }

    try:
        cabecalhos_api = {
            **CABECALHOS_HTTP,
            "Accept": "application/json",
            "Referer": url_origem,
        }

        item = obter_sfc_mais_recente(cabecalhos_api)
        ref_no = item["newsRefNo"]
        titulo = item["title"].strip()
        data_publicacao = formatar_data_iso(item["issueDate"])

        registro["url_artigo"] = SFC_URL_ARTIGO.format(ref_no=ref_no)
        registro["titulo"] = titulo
        registro["data_publicacao"] = data_publicacao

        # Conteúdo completo via API (mais confiável que o HTML da SPA)
        resposta_conteudo = requests.get(
            f"{SFC_API_BASE}/content",
            headers=cabecalhos_api,
            params={"refNo": ref_no, "lang": "EN"},
            timeout=TIMEOUT_SEGUNDOS,
        )
        resposta_conteudo.raise_for_status()
        dados_conteudo = resposta_conteudo.json()

        html_noticia = dados_conteudo.get("html", "")
        if html_noticia:
            soup = BeautifulSoup(html_noticia, "html.parser")
            texto = limpar_texto(soup.get_text(" "))
            registro["conteudo_principal"] = (
                texto[:TAMANHO_CONTEUDO] + "..." if len(texto) > TAMANHO_CONTEUDO else texto
            )
        else:
            registro["conteudo_principal"] = "Não foi possível extrair o conteúdo principal."

        registro["status"] = "sucesso"

    except Exception as erro:
        registro["mensagem_erro"] = str(erro)
        print(f"[ERRO] SFC: {erro}")

    return registro


def processar_mas(url_origem: str) -> dict:
    """
    MAS carrega a listagem via JavaScript. Usa a API Solr oficial para obter
    o Media Release mais recente (sort=mas_date_tdt desc, start=0).
    """
    registro = {
        "url_origem": url_origem,
        "url_artigo": None,
        "titulo": None,
        "data_publicacao": "Não identificada",
        "conteudo_principal": None,
        "status": "erro",
        "mensagem_erro": None,
    }

    try:
        resposta = requests.get(MAS_API_BUSCA, headers=CABECALHOS_HTTP, timeout=TIMEOUT_SEGUNDOS)
        resposta.raise_for_status()
        documento = resposta.json()["response"]["docs"][0]

        titulo = documento.get("document_title_string_s", "")
        caminho = documento.get("page_url_s", "")
        data_publicacao = formatar_data_iso(documento.get("mas_date_tdt", ""))
        link_artigo = urljoin("https://www.mas.gov.sg", caminho)

        registro["url_artigo"] = link_artigo
        registro["titulo"] = titulo
        registro["data_publicacao"] = data_publicacao

        dados_artigo = processar_artigo_html(link_artigo, titulo, data_publicacao)
        registro["titulo"] = dados_artigo["titulo"]
        registro["data_publicacao"] = dados_artigo["data_publicacao"]
        registro["conteudo_principal"] = dados_artigo["conteudo_principal"]
        registro["status"] = "sucesso"

    except Exception as erro:
        registro["mensagem_erro"] = str(erro)
        print(f"[ERRO] MAS: {erro}")

    return registro


def processar_cftc(url_origem: str) -> dict:
    """
    CFTC expõe os press releases em tabela HTML estática.
    A primeira linha (<tr>) da tabela já é o comunicado mais recente.
    """
    registro = {
        "url_origem": url_origem,
        "url_artigo": None,
        "titulo": None,
        "data_publicacao": "Não identificada",
        "conteudo_principal": None,
        "status": "erro",
        "mensagem_erro": None,
    }

    try:
        html = buscar_html(url_origem)
        if html is None:
            registro["mensagem_erro"] = "Falha na requisição HTTP"
            return registro

        soup = BeautifulSoup(html, "html.parser")
        corpo_tabela = soup.select_one("table tbody") or soup
        links = corpo_tabela.select("a[href*='/PressRoom/PressReleases/']")

        if not links:
            registro["mensagem_erro"] = "Nenhum press release encontrado na tabela"
            return registro

        # Primeiro link = comunicado mais recente da primeira página
        primeira = links[0]
        titulo = primeira.get_text(strip=True)
        link_artigo = urljoin(url_origem, primeira.get("href"))

        # Data vem da linha da tabela (coluna de data)
        data_publicacao = "Não identificada"
        linha = primeira.find_parent("tr")
        if linha:
            data = extrair_data_texto(re.sub(r"\s+", " ", linha.get_text(" ")).strip())
            if data:
                data_publicacao = data

        registro["url_artigo"] = link_artigo

        dados_artigo = processar_artigo_html(link_artigo, titulo, data_publicacao)
        registro["titulo"] = dados_artigo["titulo"]
        registro["data_publicacao"] = dados_artigo["data_publicacao"]
        registro["conteudo_principal"] = dados_artigo["conteudo_principal"]
        registro["status"] = "sucesso"

    except Exception as erro:
        registro["mensagem_erro"] = str(erro)
        print(f"[ERRO] CFTC: {erro}")

    return registro


def processar_url(url: str) -> dict:
    """Encaminha para o processador específico de cada órgão."""
    if "sfc.hk" in url:
        return processar_sfc(url)
    if "mas.gov.sg" in url:
        return processar_mas(url)
    if "cftc.gov" in url:
        return processar_cftc(url)

    return {
        "url_origem": url,
        "url_artigo": None,
        "titulo": None,
        "data_publicacao": "Não identificada",
        "conteudo_principal": None,
        "status": "erro",
        "mensagem_erro": "Órgão regulador não reconhecido",
    }


def extrair_dados_e_salvar_json() -> None:
    """Processa todos os órgãos e salva o JSON de saída."""
    resultados: list[dict] = []

    print("Iniciando extração dos itens mais recentes...\n")

    for url in URLS_REGULADORES:
        print(f"Processando: {url}")
        registro = processar_url(url)
        resultados.append(registro)

        if registro["status"] == "sucesso":
            print(f"  [OK] {registro['titulo'][:80]}")
            print(f"  Data: {registro['data_publicacao']}\n")
        else:
            print(f"  [FALHA] {registro['mensagem_erro']}\n")

    with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as arquivo:
        json.dump(resultados, arquivo, indent=4, ensure_ascii=False)

    sucessos = sum(1 for r in resultados if r["status"] == "sucesso")
    print(f"Processo concluído! {sucessos}/{len(resultados)} URLs com sucesso.")
    print(f"Arquivo '{ARQUIVO_SAIDA}' gerado com sucesso.")


if __name__ == "__main__":
    extrair_dados_e_salvar_json()
