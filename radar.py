#!/usr/bin/env python3
"""Radar de Ofertas — escolhe a melhor oferta, posta no Telegram e atualiza a vitrine.

Uso:
  python3 radar.py postar     -> posta 1 oferta no Telegram e atualiza a vitrine
  python3 radar.py vitrine    -> so atualiza a vitrine (docs/index.html)
  python3 radar.py teste      -> mostra a proxima oferta e o ranking, sem postar

Coloque as planilhas (CSV) da Shopee ou do Mercado Livre na pasta principal ou em data/.
Sem bibliotecas externas e sem IA paga: custo zero para rodar.
"""
import csv, html, json, math, os, sys, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
HIST = DATA / "postados.json"
VITRINE = BASE / "docs" / "index.html"
CANAL = os.environ.get("TELEGRAM_CHAT") or "@radardeoferta"
REPETIR_DIAS = 7          # nao repete o mesmo produto antes disso
ITENS_VITRINE = 30
BRT = timezone(timedelta(hours=-3))

# Nomes de coluna aceitos (sem acento, minusculo). Cobre CSV da Shopee em PT/EN e planilhas manuais.
COLUNAS = {
    "id": ["item id", "itemid", "id do item", "id do produto", "product id", "id"],
    "nome": ["item name", "product name", "nome do produto", "nome do item", "nome", "titulo", "name"],
    "preco": ["price", "preco", "sale price", "preco promocional", "preco atual", "preco por", "price(min)", "preco minimo"],
    "preco_original": ["original price", "preco original", "preco de", "price before discount", "preco cheio"],
    "desconto": ["discount", "desconto", "discount rate", "% desconto"],
    "vendas": ["sales", "vendas", "sold", "item sold", "historical sold", "vendidos", "quantidade vendida"],
    "comissao": ["commission", "comissao", "estimated commission", "comissao estimada", "ganho", "comissao (r$)"],
    "taxa": ["commission rate", "taxa de comissao", "comissao (%)", "taxa"],
    "link": ["offer link", "link da oferta", "link de afiliado", "affiliate link", "short link", "link curto", "link"],
    "imagem": ["image link", "image", "image url", "imagem", "link da imagem", "product image"],
}


def _norm(txt):
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    return " ".join(txt.lower().replace("_", " ").split())


def _num(valor):
    """Converte 'R$ 1.234,56', '12%', '1,2mil', '10k+' em numero."""
    if valor is None:
        return 0.0
    s = _norm(valor).replace("r$", "").replace("%", "").replace("+", "").strip()
    mult = 1
    if s.endswith("mil"):
        mult, s = 1000, s[:-3].strip()
    elif s.endswith("k"):
        mult, s = 1000, s[:-1].strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3 and mult == 1:
        s = s.replace(".", "")  # 1.234 (milhar)
    try:
        return float("".join(c for c in s if c.isdigit() or c in ".-")) * mult
    except ValueError:
        return 0.0


def carregar_produtos():
    produtos = {}
    for arq in sorted(set(DATA.glob("*.csv")) | set(BASE.glob("*.csv"))):
        texto = arq.read_bytes().decode("utf-8-sig", errors="replace")
        amostra = texto[:2000]
        sep = ";" if amostra.count(";") > amostra.count(",") else ","
        leitor = csv.DictReader(texto.splitlines(), delimiter=sep)
        mapa = {}
        cols = {_norm(c): c for c in leitor.fieldnames or []}
        for campo, nomes in COLUNAS.items():
            for nome in nomes:  # respeita a ordem de prioridade (ex.: link de afiliado antes de link)
                if nome in cols:
                    mapa[campo] = cols[nome]
                    break
        if "nome" not in mapa or "link" not in mapa or "preco" not in mapa:
            print(f"[aviso] {arq.name}: colunas de nome/preco/link nao encontradas, ignorado")
            continue
        for linha in leitor:
            p = {c: (linha.get(col) or "").strip() for c, col in mapa.items()}
            if not p.get("nome") or not p.get("link", "").startswith("http"):
                continue
            preco = _num(p.get("preco"))
            if preco <= 0:
                continue
            orig = _num(p.get("preco_original"))
            desc = _num(p.get("desconto"))
            if not desc and orig > preco:
                desc = round((1 - preco / orig) * 100)
            # sem dado de comissao (planilha manual do ML): estima 5% so para o ranking
            comissao = _num(p.get("comissao")) or preco * (_num(p.get("taxa")) or 5) / 100
            vendas = _num(p.get("vendas"))
            # Ranking: comissao em R$ x volume de vendas (em log, p/ nao dominar) x peso do desconto
            score = max(comissao, 0.01) * math.log10(vendas + 10) * (1 + min(desc, 90) / 100)
            pid = p.get("id") or p["link"]
            item = {"id": pid, "nome": p["nome"][:120], "preco": preco, "preco_original": orig,
                    "desconto": int(desc), "link": p["link"], "imagem": p.get("imagem", ""),
                    "score": score}
            if pid not in produtos or produtos[pid]["score"] < score:
                produtos[pid] = item
    return sorted(produtos.values(), key=lambda x: x["score"], reverse=True)


def ler_historico():
    try:
        return json.loads(HIST.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def escolher(produtos, hist):
    limite = datetime.now(BRT) - timedelta(days=REPETIR_DIAS)
    for p in produtos:
        quando = hist.get(p["id"])
        if not quando or datetime.fromisoformat(quando) < limite:
            return p
    # todos postados recentemente: repete o mais antigo
    return min(produtos, key=lambda p: hist.get(p["id"], "")) if produtos else None


def reais(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def texto_post(p):
    linhas = ["🔴 RADAR LIGADO", "", p["nome"], ""]
    if p["preco_original"] > p["preco"]:
        linhas.append(f"De {reais(p['preco_original'])} por {reais(p['preco'])} 🔥")
    else:
        linhas.append(f"Por {reais(p['preco'])} 🔥")
    if p["desconto"] >= 5:
        linhas.append(f"📉 {p['desconto']}% OFF")
    linhas += ["", f"👉 {p['link']}", "", "⏳ Oferta imperdível"]
    return "\n".join(linhas)


def telegram(metodo, dados):
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        sys.exit("Falta o segredo TELEGRAM_TOKEN.")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{metodo}",
        data=urllib.parse.urlencode(dados).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def postar(p):
    texto = texto_post(p)
    if p["imagem"].startswith("http"):
        try:
            return telegram("sendPhoto", {"chat_id": CANAL, "photo": p["imagem"], "caption": texto[:1024]})
        except Exception as e:  # imagem quebrada: posta so o texto
            print(f"[aviso] foto falhou ({e}), enviando so texto")
    return telegram("sendMessage", {"chat_id": CANAL, "text": texto})


def gerar_vitrine(produtos):
    canal_link = f"https://t.me/{CANAL.lstrip('@')}"
    cards = []
    for p in produtos[:ITENS_VITRINE]:
        e = html.escape
        img = f'<img src="{e(p["imagem"])}" alt="" loading="lazy">' if p["imagem"].startswith("http") else '<div class="sem-img">📡</div>'
        de = f'<s>{reais(p["preco_original"])}</s>' if p["preco_original"] > p["preco"] else ""
        selo = f'<span class="selo">-{p["desconto"]}%</span>' if p["desconto"] >= 5 else ""
        cards.append(f'''<a class="card" href="{e(p["link"])}" target="_blank" rel="nofollow sponsored noopener">
<div class="foto">{img}{selo}</div><div class="info"><h2>{e(p["nome"])}</h2>
<p class="preco">{de}<b>{reais(p["preco"])}</b></p><span class="btn">Ver oferta</span></div></a>''')
    agora = datetime.now(BRT).strftime("%d/%m/%Y às %Hh%M")
    pagina = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radar de Ofertas</title><meta name="description" content="A IA que caça preço baixo por você. Ofertas da Shopee e do Mercado Livre atualizadas todo dia.">
<style>
:root{{--bg:#0b0f0c;--card:#141a16;--txt:#eef5ef;--sub:#93a397;--verde:#2bff88;--verm:#ff4d4d}}
*{{box-sizing:border-box;margin:0;padding:0}}body{{background:var(--bg);color:var(--txt);font:16px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
header{{padding:28px 16px 18px;text-align:center}}.logo{{font-size:28px;font-weight:800;letter-spacing:-.5px}}.logo span{{color:var(--verde)}}
.tag{{color:var(--sub);margin-top:4px}}.cta{{display:inline-block;margin-top:16px;background:var(--verde);color:#04140a;font-weight:700;padding:12px 22px;border-radius:999px;text-decoration:none}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;padding:8px 16px 32px;max-width:1100px;margin:0 auto}}
.card{{background:var(--card);border-radius:14px;overflow:hidden;color:inherit;text-decoration:none;display:flex;flex-direction:column}}
.foto{{position:relative;aspect-ratio:1;background:#fff}}.foto img{{width:100%;height:100%;object-fit:cover}}.sem-img{{display:grid;place-items:center;height:100%;font-size:40px;background:#1c241f}}
.selo{{position:absolute;top:8px;left:8px;background:var(--verm);color:#fff;font-weight:700;font-size:13px;padding:3px 8px;border-radius:8px}}
.info{{padding:10px;display:flex;flex-direction:column;gap:6px;flex:1}}h2{{font-size:14px;font-weight:500;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.preco s{{color:var(--sub);font-size:13px;margin-right:6px}}.preco b{{color:var(--verde);font-size:18px}}
.btn{{margin-top:auto;text-align:center;border:1px solid var(--verde);color:var(--verde);border-radius:10px;padding:7px;font-size:14px;font-weight:600}}
footer{{text-align:center;color:var(--sub);font-size:12px;padding:0 16px 28px}}
</style></head><body>
<header><div class="logo">📡 Radar de <span>Ofertas</span></div><p class="tag">A IA que caça preço baixo por você</p>
<a class="cta" href="{canal_link}">Receber ofertas no Telegram</a></header>
<main>{"".join(cards) or "<p>Novas ofertas em breve.</p>"}</main>
<footer>Atualizado em {agora} · Preços podem mudar a qualquer momento · Links de afiliado</footer>
</body></html>'''
    VITRINE.parent.mkdir(exist_ok=True)
    VITRINE.write_text(pagina, encoding="utf-8")


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "teste"
    produtos = carregar_produtos()
    if not produtos:
        print("Nenhum produto encontrado em data/*.csv. Suba a planilha da Shopee na pasta data/.")
        gerar_vitrine([])
        return
    gerar_vitrine(produtos)
    hist = ler_historico()
    p = escolher(produtos, hist)
    if modo == "teste":
        print(f"{len(produtos)} produtos carregados. Top 5:")
        for i, x in enumerate(produtos[:5], 1):
            print(f"  {i}. {x['nome'][:60]} | {reais(x['preco'])} | score {x['score']:.1f}")
        print("\n--- Proximo post ---\n" + texto_post(p))
        return
    if modo == "postar":
        r = postar(p)
        if not r.get("ok"):
            sys.exit(f"Telegram recusou: {r}")
        hist[p["id"]] = datetime.now(BRT).isoformat(timespec="minutes")
        DATA.mkdir(exist_ok=True)
        HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=1))
        print(f"Postado: {p['nome']}")


if __name__ == "__main__":
    main()
