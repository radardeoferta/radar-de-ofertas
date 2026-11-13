#!/usr/bin/env python3
"""Radar de Ofertas — TikTok automatico via Zernio (plano gratis).

  python3 tiktok.py teste     -> mostra a conta TikTok conectada e salva data/zernio_info.json
  python3 tiktok.py preparar  -> cria as imagens 1080x1920 (JPG) em docs/series/<serie>/tiktok/
  python3 tiktok.py agendar   -> agenda no TikTok os posts do series.txt com DATA/HORA ainda nao agendados

Postar agora: escreva o TITULO do post (um por linha) em tiktok_agora.txt e suba no GitHub.

Horario do TikTok: post das 12h vai as 13h, post das 20h vai as 19h30.
Para mudar um post, coloque no bloco do series.txt a linha  HORA_TIKTOK: 18h30
Musica: o TikTok coloca sozinho uma musica recomendada (auto_add_music).

Precisa do segredo ZERNIO_API_KEY. Nunca grava a chave em arquivo.
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from buffer import BASE, BRT, SITE, esperar_url, ler_posts, quando, slug

API = "https://zernio.com/api/v1"
INFO = BASE / "data" / "zernio_info.json"
FEITOS = BASE / "data" / "tiktok_agendados.json"
AGORA = BASE / "tiktok_agora.txt"
ROTULO_IA = "Imagem gerada por IA."


def api(metodo, caminho, corpo=None):
    chave = os.environ.get("ZERNIO_API_KEY")
    if not chave:
        sys.exit("Falta o segredo ZERNIO_API_KEY.")
    req = urllib.request.Request(f"{API}{caminho}", method=metodo,
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json",
                                          "User-Agent": "radar-de-ofertas"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        corpo = e.read().decode(errors="replace")[:2000]
        try:
            return e.code, json.loads(corpo)
        except ValueError:
            return e.code, {"erro": corpo}


def conta_tiktok():
    st, r = api("GET", "/accounts")
    contas = r.get("accounts") or r.get("data") or (r if isinstance(r, list) else [])
    for c in contas:
        if str(c.get("platform", "")).lower() == "tiktok":
            return c.get("_id") or c.get("accountId") or c.get("id"), c
    sys.exit(f"Nenhuma conta TikTok conectada no Zernio. Resposta ({st}): {json.dumps(r)[:800]}")


def info_criador(conta_id):
    st, r = api("GET", f"/accounts/{conta_id}/tiktok/creator-info?mediaType=photo")
    return r if st < 300 else {}


def teste():
    conta_id, conta = conta_tiktok()
    criador = info_criador(conta_id)
    resumo = {"conta_id": conta_id, "usuario": conta.get("username") or conta.get("displayName"),
              "criador": criador}
    INFO.parent.mkdir(exist_ok=True)
    INFO.write_text(json.dumps(resumo, ensure_ascii=False, indent=1))
    print(json.dumps(resumo, ensure_ascii=False)[:2000])
    feitos = json.loads(FEITOS.read_text()) if FEITOS.exists() else {}
    for nome, reg in feitos.items():
        st, r = api("GET", f"/posts/{reg['id']}")
        post = r.get("post") or r
        ts = {}
        for pl in post.get("platforms") or []:
            ts = (pl.get("platformSpecificData") or {}).get("tiktokSettings") or ts
        print("conferir", nome, st, post.get("status"), "privacidade=", json.dumps(ts.get("privacy_level")),
              "musica=", ts.get("auto_add_music"))


# ---------------- imagens 1080x1920 ----------------
def preparar():
    from PIL import Image, ImageFilter, ImageEnhance
    feitos = 0
    for p in ler_posts():
        pasta = BASE / "docs" / "series" / slug(p["titulo"])
        pngs = sorted(pasta.glob("[0-9][0-9].png"))
        if not pngs:
            continue
        saida = pasta / "tiktok"
        saida.mkdir(exist_ok=True)
        for png in pngs:
            jpg = saida / (png.stem + ".jpg")
            if jpg.exists() and jpg.stat().st_mtime >= png.stat().st_mtime:
                continue
            img = Image.open(png).convert("RGB")
            img.thumbnail((1080, 1920), Image.LANCZOS)
            # fundo: a propria imagem ampliada e desfocada, para preencher 9:16 sem cortar nada
            esc = max(1080 / img.width, 1920 / img.height)
            fundo = img.resize((round(img.width * esc), round(img.height * esc)), Image.LANCZOS)
            l, t = (fundo.width - 1080) // 2, (fundo.height - 1920) // 2
            fundo = fundo.crop((l, t, l + 1080, t + 1920)).filter(ImageFilter.GaussianBlur(40))
            fundo = ImageEnhance.Brightness(fundo).enhance(0.9)
            fundo.paste(img, ((1080 - img.width) // 2, (1920 - img.height) // 2))
            fundo.save(jpg, "JPEG", quality=90, optimize=True, progressive=True)
            feitos += 1
    print(f"imagens TikTok geradas: {feitos}")


# ---------------- agendamento ----------------
def quando_tiktok(p):
    base = quando(p)
    extra = p.get("hora_tiktok")
    if extra:
        m = re.search(r"(\d{1,2})\s*[h:]?\s*(\d{2})?", extra)
        return base.replace(hour=int(m.group(1)), minute=int(m.group(2) or 0))
    if base.hour == 12:
        return base.replace(hour=13, minute=0)
    if base.hour == 20:
        return base.replace(hour=19, minute=30)
    return base


def legenda(p):
    texto = p.get("legenda", "").replace("\\n", " ")
    texto = re.sub(r"\s+", " ", texto).strip()  # a API do TikTok nao aceita quebra de linha
    return f"{texto} {ROTULO_IA}".strip()[:4000]


def enviar(p, conta_id, privacidade, hora=None):
    """Agenda (hora) ou publica agora (hora=None). Devolve o registro ou None."""
    s = slug(p["titulo"])
    jpgs = sorted((BASE / "docs" / "series" / s / "tiktok").glob("*.jpg"))
    if not jpgs:
        print(f"[aviso] sem imagens TikTok para {s}")
        return None
    urls = [f"{SITE}/series/{s}/tiktok/{j.name}" for j in jpgs][:35]
    if not esperar_url(urls[-1], limite=900):
        print(f"[aviso] imagens ainda nao estao no site: {s}")
        return None
    corpo = {
        "content": p.get("post", p["titulo"])[:90],
        "mediaItems": [{"type": "image", "url": u} for u in urls],
        "platforms": [{"platform": "tiktok", "accountId": conta_id}],
        "tiktokSettings": {
            "media_type": "photo",
            "photo_cover_index": 0,
            "description": legenda(p),
            "auto_add_music": True,
            "privacy_level": privacidade,
            "allow_comment": True,
            "content_preview_confirmed": True,
            "express_consent_given": True,
        },
    }
    if hora:
        corpo.update({"scheduledFor": hora.strftime("%Y-%m-%dT%H:%M:00"), "timezone": "America/Sao_Paulo"})
    else:
        corpo["publishNow"] = True
    st, r = api("POST", "/posts", corpo)
    post = r.get("post") or {}
    ok = st < 300 and post.get("status") in ("scheduled", "publishing", "published")
    rotulo = hora.strftime("%d/%m %H:%M") if hora else "AGORA"
    print("tiktok", s, rotulo, "OK" if ok else f"ERRO {st}: {json.dumps(r)[:600]}")
    if ok:
        return {"id": post.get("_id"), "quando": (hora or datetime.now(BRT)).isoformat()}
    return None


def corrigir(feitos):
    """Apaga e libera para recriar os agendados com privacidade em formato errado (bug de 01/11)."""
    for nome, reg in list(feitos.items()):
        st, r = api("GET", f"/posts/{reg['id']}")
        post = r.get("post") or r
        if post.get("status") != "scheduled":
            continue
        ts = {}
        for pl in post.get("platforms") or []:
            ts = (pl.get("platformSpecificData") or {}).get("tiktokSettings") or ts
        if isinstance(ts.get("privacy_level"), str):
            continue
        st, r = api("DELETE", f"/posts/{reg['id']}")
        print("corrigir", nome, "apagado" if st < 300 else f"ERRO ao apagar {st}: {json.dumps(r)[:300]}")
        if st < 300:
            del feitos[nome]
            FEITOS.write_text(json.dumps(feitos, ensure_ascii=False, indent=1))


def agendar():
    conta_id, _ = conta_tiktok()
    criador = info_criador(conta_id)
    niveis = [n.get("value", n) if isinstance(n, dict) else n
              for n in (criador.get("privacyLevels") or criador.get("privacy_level_options") or [])]
    privacidade = "PUBLIC_TO_EVERYONE" if not niveis or "PUBLIC_TO_EVERYONE" in niveis else niveis[0]
    feitos = json.loads(FEITOS.read_text()) if FEITOS.exists() else {}
    posts = ler_posts()
    corrigir(feitos)

    def salvar():
        FEITOS.write_text(json.dumps(feitos, ensure_ascii=False, indent=1))

    # 1) postar agora o que estiver em tiktok_agora.txt
    if AGORA.exists():
        pedidos = [slug(l) for l in AGORA.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        for pedido in pedidos:
            p = next((x for x in posts if slug(x["titulo"]) == pedido or slug(x.get("post", "")) == pedido), None)
            if not p:
                print(f"[aviso] post nao encontrado no series.txt: {pedido}")
                continue
            if feitos.get(slug(p["titulo"])):
                print(f"[aviso] ja foi para o TikTok: {pedido}")
                continue
            reg = enviar(p, conta_id, privacidade)
            if reg:
                feitos[slug(p["titulo"])] = reg
                salvar()
        AGORA.write_text("# Escreva aqui o TITULO do post para postar agora no TikTok (um por linha)\n", encoding="utf-8")

    # 2) agendar os proximos
    agora = datetime.now(BRT)
    for p in posts:
        s = slug(p["titulo"])
        if feitos.get(s):
            continue
        hora = quando_tiktok(p)
        if hora < agora + timedelta(minutes=20):
            continue
        reg = enviar(p, conta_id, privacidade, hora)
        if reg:
            feitos[s] = reg
            salvar()


def cancelar():
    """Para tudo da Nina: apaga no Zernio os posts ainda agendados e lista os ja publicados."""
    feitos = json.loads(FEITOS.read_text()) if FEITOS.exists() else {}
    publicados = []
    for nome, reg in list(feitos.items()):
        st, r = api("GET", f"/posts/{reg['id']}")
        post = r.get("post") or r
        status = post.get("status")
        if status in ("scheduled", "draft", "pending"):
            st, r = api("DELETE", f"/posts/{reg['id']}")
            print("cancelado", nome, reg["quando"][:16], "OK" if st < 300 else f"ERRO {st}: {json.dumps(r)[:300]}")
            if st < 300:
                feitos[nome] = {**reg, "cancelado": True}
        else:
            publicados.append((reg["quando"][:16], nome, status))
    FEITOS.write_text(json.dumps(feitos, ensure_ascii=False, indent=1))
    for quando, nome, status in sorted(publicados):
        print("publicado", quando, nome, status)


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "teste"
    {"teste": teste, "preparar": preparar, "agendar": agendar, "cancelar": cancelar}.get(modo, teste)()
