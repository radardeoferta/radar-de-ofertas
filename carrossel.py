#!/usr/bin/env python3
"""Radar de Ofertas — gera carrosseis no estilo Pinterest "da serie" (capa + produtos + final).

Le:   series.txt, fotos/ (persona), produtos/<item_id>.jpg|png|webp (foto do produto) e a planilha *.csv
Gera: docs/series/<serie>/01.png, 02.png... (1080x1440, 3:4 — serve no Pinterest, Instagram e TikTok)
      docs/series/<serie>/index.html (pagina da serie, link do pin) e docs/painel.html (baixar tudo)
"""
import base64, html, mimetypes, re, sys, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radar

BASE = Path(__file__).resolve().parent
SAIDA = BASE / "docs" / "series"
W, H = 1080, 1440
CANAL = radar.CANAL.lstrip("@")
PERFIL = "@radardeoferta_oficial"
SITE = "https://radardeoferta.github.io/radar-de-ofertas"

FONTES = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Great+Vibes&family=Montserrat:wght@500;600;700'
          '&family=Playfair+Display:ital,wght@0,600;0,700;1,600;1,700&display=swap">')
_FL = BASE / "fonts"  # testes locais sem internet
if _FL.exists():
    def _ff(nome, arq, estilo="normal"):
        return (f"@font-face{{font-family:'{nome}';font-style:{estilo};font-weight:100 900;"
                f"src:url(data:font/ttf;base64,{base64.b64encode((_FL / arq).read_bytes()).decode()})}}")
    FONTES = "<style>" + _ff("Playfair Display", "Playfair.ttf") + _ff("Playfair Display", "PlayfairItalic.ttf", "italic") \
        + _ff("Montserrat", "Montserrat.ttf") + _ff("Great Vibes", "GreatVibes.ttf") + "</style>"

# Paleta: rose antigo, blush, nude e branco
CSS = """
:root{--rose:#D58A9E;--rose2:#C27088;--blush:#F6DCE3;--nude:#F4EAE4;--cacau:#3A2E2C}
*{margin:0;padding:0;box-sizing:border-box}
body{width:%dpx;height:%dpx;overflow:hidden;position:relative;font-family:Montserrat,sans-serif}
.script{font-family:'Great Vibes',cursive;font-weight:400}
.serif{font-family:'Playfair Display',Georgia,serif}
.handle{position:absolute;bottom:38px;left:0;right:0;text-align:center;font:600 22px Montserrat;letter-spacing:2px;color:rgba(255,255,255,.85)}
.brilho{position:absolute;width:46px;height:46px;fill:#fff}
""" % (W, H)
CORACAO = '<svg viewBox="0 0 24 24" width="34" height="34"><path fill="#fff" d="M12 21s-7.5-4.6-9.6-9.2C.8 8.2 3 4.5 6.6 4.5c2 0 3.5 1.1 4.4 2.6.9-1.5 2.4-2.6 4.4-2.6 3.6 0 5.8 3.7 4.2 7.3C19.5 16.4 12 21 12 21z"/></svg>'
BRILHO = '<svg class="brilho" viewBox="0 0 24 24" style="{pos}"><path d="M12 0c.6 6.4 5.6 11.4 12 12-6.4.6-11.4 5.6-12 12C11.4 17.6 6.4 12.6 0 12 6.4 11.4 11.4 6.4 12 0z"/></svg>'


def slug(txt):
    t = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:50]


def data_uri(arq):
    tipo = mimetypes.guess_type(arq.name)[0] or "image/jpeg"
    return f"data:{tipo};base64,{base64.b64encode(arq.read_bytes()).decode()}"


def nome_curto(nome, limite=6):
    nome = re.sub(r"[^\w\s%,./&+-]", "", nome).strip()
    p = nome.split()
    return " ".join(p[:limite]) + ("…" if len(p) > limite else "")


def ler_series():
    series = []
    for bloco in re.split(r"\n\s*\n", (BASE / "series.txt").read_text(encoding="utf-8")):
        s = {"produtos": []}
        for linha in bloco.splitlines():
            if linha.strip().startswith("#") or ":" not in linha:
                continue
            chave, valor = (x.strip() for x in linha.split(":", 1))
            if chave.upper() == "PRODUTO":
                pid, _, apelido = valor.partition("|")
                s["produtos"].append((pid.strip(), apelido.strip()))
            else:
                s[chave.lower()] = valor
        if s.get("titulo") and s["produtos"]:
            series.append(s)
    return series


def titulo_html(titulo, destaque):
    if destaque and destaque.lower() in titulo.lower():
        i = titulo.lower().index(destaque.lower())
        return (html.escape(titulo[:i]) + f"<mark>{html.escape(titulo[i:i + len(destaque)])}</mark>"
                + html.escape(titulo[i + len(destaque):]))
    return html.escape(titulo)


def capa(s, foto):
    fundo = f"url('{data_uri(foto)}') center/cover" if foto else "linear-gradient(170deg,#e9d7cc,#b89584)"
    n = len(s["titulo"])
    tam = 112 if n <= 30 else 98 if n <= 40 else 86 if n <= 52 else 74
    return f"""<html><head>{FONTES}<style>{CSS}
body{{background:{fundo}}}
.sombra{{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0) 30%,rgba(30,18,16,.42) 52%,rgba(30,18,16,.8) 100%)}}
.txt{{position:absolute;left:50px;right:50px;bottom:120px;text-align:center;color:#fff}}
.selo{{display:inline-block;transform:rotate(-5deg);background:var(--rose);padding:2px 34px 12px;border-radius:14px;
  font-size:78px;line-height:1;color:#fff;box-shadow:0 6px 18px rgba(0,0,0,.18);margin-bottom:18px}}
h1{{font:700 {tam}px/1.3 'Playfair Display',serif;letter-spacing:-1px;text-shadow:0 3px 22px rgba(0,0,0,.45)}}
mark{{background:var(--rose);color:#fff;font-style:italic;padding:0 16px 2px;border-radius:10px;
  box-decoration-break:clone;-webkit-box-decoration-break:clone;text-shadow:none}}
.linha{{display:flex;align-items:center;gap:16px;margin:34px 40px 0}}
.linha:before,.linha:after{{content:"";height:3px;flex:1;background:#fff;border-radius:3px}}
.sub{{margin-top:16px;font:600 30px Montserrat;letter-spacing:5px;text-transform:uppercase;text-shadow:0 2px 10px rgba(0,0,0,.4)}}
</style></head><body><div class="sombra"></div>
{BRILHO.format(pos="top:860px;right:70px")}{BRILHO.format(pos="top:930px;right:130px;width:26px;height:26px")}
<div class="txt"><div class="selo script">da série:</div>
<h1>{titulo_html(s["titulo"], s.get("destaque", ""))}</h1>
<div class="linha">{CORACAO}</div><div class="sub">{html.escape(s.get("subtitulo", "achadinhos da Shopee"))}</div></div>
<div class="handle">{PERFIL}</div></body></html>"""


def slide_produto(p, apelido, foto_prod, foto_serie=None, num=1):
    nome = html.escape(apelido or nome_curto(p["nome"]))
    de = f'<s>{radar.reais(p["preco_original"])}</s>' if p["preco_original"] > p["preco"] else ""
    if foto_prod:
        uri = data_uri(foto_prod)
        fundo = (f'<div style="position:absolute;inset:-40px;background:url(\'{uri}\') center/cover;filter:blur(28px) brightness(.9)"></div>'
                 f'<div style="position:absolute;inset:0;background:url(\'{uri}\') center/contain no-repeat"></div>')
    else:
        return slide_lista(p, nome, de, foto_serie, num)
    return f"""<html><head>{FONTES}<style>{CSS}
.topo{{position:absolute;top:0;left:0;right:0;height:430px;background:linear-gradient(180deg,rgba(30,18,16,.62),rgba(30,18,16,0))}}
.cap{{position:absolute;top:70px;left:60px;right:60px;text-align:center;color:#fff}}
h2{{font:700 64px/1.12 'Playfair Display',serif;text-shadow:0 3px 18px rgba(0,0,0,.5)}}
.preco{{margin-top:22px;display:inline-flex;align-items:center;gap:16px;background:#fff;border-radius:999px;padding:12px 30px;
  box-shadow:0 6px 18px rgba(0,0,0,.18)}}
.preco b{{font:700 44px Montserrat;color:var(--rose2)}}.preco s{{font:600 28px Montserrat;color:#a39592}}
.dica{{position:absolute;bottom:90px;left:50%;transform:translateX(-50%);background:var(--rose);color:#fff;white-space:nowrap;
  font:600 26px Montserrat;letter-spacing:3px;padding:14px 32px;border-radius:999px;text-transform:uppercase;box-shadow:0 6px 18px rgba(0,0,0,.18)}}
</style></head><body>{fundo}<div class="topo"></div>
<div class="cap"><h2>{nome}</h2><div class="preco"><b>{radar.reais(p["preco"])}</b>{de}</div></div>
<div class="dica">link na bio ♡</div><div class="handle">{PERFIL}</div></body></html>"""


def slide_lista(p, nome, de, foto, num):
    fundo = f"url('{data_uri(foto)}') center/cover" if foto else "var(--nude)"
    return f"""<html><head>{FONTES}<style>{CSS}
body{{background:{fundo}}}
.vela{{position:absolute;inset:0;background:rgba(244,234,228,.84);backdrop-filter:blur(6px)}}
.box{{position:absolute;left:90px;right:90px;top:50%;transform:translateY(-52%);text-align:center;color:var(--cacau)}}
.num{{font-size:150px;line-height:1;color:var(--rose2)}}
h2{{font:700 76px/1.14 'Playfair Display',serif;margin-top:6px}}
.preco{{margin-top:40px;display:inline-flex;align-items:center;gap:18px;background:var(--rose);border-radius:999px;padding:16px 40px}}
.preco b{{font:700 50px Montserrat;color:#fff}}.preco s{{font:600 30px Montserrat;color:rgba(255,255,255,.75)}}
.dica{{margin-top:40px;font:600 28px Montserrat;letter-spacing:5px;text-transform:uppercase;color:var(--rose2)}}
.handle{{color:var(--cacau)}}
</style></head><body><div class="vela"></div><div class="box"><div class="num script">achado {num}</div>
<h2>{nome}</h2><div class="preco"><b>{radar.reais(p["preco"])}</b>{de}</div><div class="dica">link na bio ♡</div></div>
<div class="handle">{PERFIL}</div></body></html>"""


def slide_final(foto):
    fundo = f"url('{data_uri(foto)}') center/cover" if foto else "linear-gradient(170deg,var(--blush),var(--rose))"
    return f"""<html><head>{FONTES}<style>{CSS}
body{{background:{fundo}}}
.vela{{position:absolute;inset:0;background:rgba(244,234,228,.78)}}
.box{{position:absolute;left:80px;right:80px;top:50%;transform:translateY(-50%);text-align:center;color:var(--cacau)}}
.script{{font-size:120px;color:var(--rose2);line-height:1}}
h2{{font:700 78px/1.12 'Playfair Display',serif;margin-top:10px}}
p{{margin-top:34px;font:600 32px/1.6 Montserrat}}
.cta{{display:inline-block;margin-top:44px;background:var(--rose);color:#fff;font:700 28px Montserrat;letter-spacing:4px;
  padding:22px 44px;border-radius:999px;text-transform:uppercase}}
.handle{{color:var(--cacau)}}
</style></head><body><div class="vela"></div><div class="box"><div class="script">Gostou?</div>
<h2>Salva pra não perder ♡</h2><p>Todos os links estão na bio<br>e tem achadinho novo todo dia</p>
<div class="cta">Link na bio</div></div><div class="handle">{PERFIL}</div></body></html>"""


def pagina_serie(s, itens, capa_url):
    cards = "".join(
        f'<a class="card" href="{html.escape(p["link"])}" target="_blank" rel="nofollow sponsored noopener">'
        f'<span class="n">{i:02d}</span><span class="t">{html.escape(ap or nome_curto(p["nome"], 10))}</span>'
        f'<b>{radar.reais(p["preco"])}</b><span class="btn">Ver na Shopee ♡</span></a>'
        for i, (p, ap) in enumerate(itens, 1))
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(s["titulo"])} · Radar de Ofertas</title><meta property="og:image" content="{capa_url}">{FONTES}
<style>:root{{--rose:#D58A9E;--rose2:#C27088;--nude:#F4EAE4;--cacau:#3A2E2C}}*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--nude);color:var(--cacau);font:16px/1.4 Montserrat,sans-serif;max-width:640px;margin:0 auto;padding:28px 16px 40px}}
.k{{font:30px 'Great Vibes',cursive;color:var(--rose2)}}h1{{font:700 30px/1.15 'Playfair Display',serif;margin:0 0 22px}}
.card{{display:grid;grid-template-columns:44px 1fr auto;gap:4px 12px;align-items:center;background:#fff;border-radius:16px;padding:14px 16px;margin-bottom:10px;color:inherit;text-decoration:none;box-shadow:0 2px 10px rgba(58,46,44,.07)}}
.n{{font:italic 700 26px 'Playfair Display',serif;color:var(--rose2);grid-row:span 2}}.t{{font-weight:600}}b{{color:var(--rose2);font-size:18px}}
.btn{{grid-column:2/4;font-size:13px;font-weight:700;color:var(--rose2);letter-spacing:1px;text-transform:uppercase}}
.tg{{display:block;text-align:center;margin-top:22px;background:var(--rose);color:#fff;font-weight:700;padding:14px;border-radius:999px;text-decoration:none}}
footer{{text-align:center;color:#8d7f7b;font-size:12px;margin-top:18px}}</style></head><body>
<div class="k">da série:</div><h1>{html.escape(s["titulo"])}</h1>{cards}
<a class="tg" href="https://t.me/{CANAL}">Receber achadinhos todo dia no Telegram</a>
<footer>Preços podem mudar a qualquer momento · Links de afiliado</footer></body></html>"""


def main():
    from playwright.sync_api import sync_playwright
    produtos = {p["id"]: p for p in radar.carregar_produtos()}
    pasta_fotos, pasta_prod = BASE / "fotos", BASE / "produtos"
    fotos = sorted(f for f in pasta_fotos.glob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) if pasta_fotos.exists() else []
    painel = []
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pag = nav.new_page(viewport={"width": W, "height": H})

        def png(doc, destino):
            pag.set_content(doc, wait_until="networkidle")
            pag.wait_for_timeout(300)
            pag.screenshot(path=str(destino))

        for k, s in enumerate(ler_series()):
            itens = [(produtos[pid], ap) for pid, ap in s["produtos"] if pid in produtos]
            faltam = [pid for pid, _ in s["produtos"] if pid not in produtos]
            if faltam:
                print(f"[aviso] {s['titulo']}: fora da planilha: {', '.join(faltam)}")
            if not itens:
                continue
            escolhida = pasta_fotos / s.get("foto", "-")
            foto = escolhida if escolhida.is_file() else (fotos[k % len(fotos)] if fotos else None)
            pasta = SAIDA / slug(s["titulo"])
            pasta.mkdir(parents=True, exist_ok=True)
            for velho in pasta.glob("*.png"):
                velho.unlink()
            png(capa(s, foto), pasta / "01.png")
            n = 2
            for p, ap in itens:
                fp = next(iter(pasta_prod.glob(f"{p['id']}.*")), None) if pasta_prod.exists() else None
                png(slide_produto(p, ap, fp, foto, n - 1), pasta / f"{n:02d}.png")
                n += 1
            png(slide_final(foto), pasta / f"{n:02d}.png")
            url = f"{SITE}/series/{slug(s['titulo'])}/"
            imgs = [f"{url}{i:02d}.png" for i in range(1, n + 1)]
            (pasta / "index.html").write_text(pagina_serie(s, itens, imgs[0]), encoding="utf-8")
            painel.append((s, url, imgs))
            print(f"OK: {s['titulo']} ({n} imagens)")
        nav.close()

    blocos = "".join(
        f'<section><h2>{html.escape(s["titulo"])}</h2><p>Link do pin: <a href="{u}">{u}</a></p><div class="g">'
        + "".join(f'<a href="{i}" download><img src="{i}" loading="lazy"></a>' for i in imgs) + "</div></section>"
        for s, u, imgs in painel)
    (BASE / "docs" / "painel.html").write_text(
        f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Painel de carrosseis</title><style>body{{font:15px system-ui;background:#F4EAE4;margin:0;padding:20px}}
section{{background:#fff;border-radius:12px;padding:16px;margin-bottom:16px}}h2{{margin:0 0 6px}}.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin-top:10px}}
img{{width:100%;border-radius:8px}}</style></head><body><h1>Carrosseis prontos</h1><p>Toque numa imagem e salve. Poste na ordem 01, 02, 03...</p>{blocos}</body></html>""",
        encoding="utf-8")


if __name__ == "__main__":
    main()
