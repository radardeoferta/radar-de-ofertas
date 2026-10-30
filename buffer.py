#!/usr/bin/env python3
"""Radar de Ofertas — conexao com o Buffer (Instagram + Pinterest).

  python3 buffer.py descobrir  -> salva data/buffer_info.json (organizacao, canais, pastas, esquema da API)
  python3 buffer.py agendar    -> agenda no Buffer os posts do series.txt que tem DATA/HORA e ainda nao foram agendados

Precisa do segredo BUFFER_TOKEN. Nunca grava a chave em arquivo.
"""
import json, os, sys, urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
INFO = BASE / "data" / "buffer_info.json"
API = "https://api.buffer.com"


def gql(query, variables=None):
    token = os.environ.get("BUFFER_TOKEN")
    if not token:
        sys.exit("Falta o segredo BUFFER_TOKEN.")
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                                          "User-Agent": "radar-de-ofertas"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode(errors="replace")[:2000]}


TIPOS = ["CreatePostInput", "AssetInput", "ImageAssetInput", "PostInputMetaData", "InstagramPostMetadataInput",
         "PinterestPostMetadataInput", "ShareMode", "SchedulingType", "PostType", "Channel", "PinterestBoard",
         "CreatePostPayload", "PostActionSuccess", "MutationError", "ChannelMetadata", "PinterestMetadata",
         "Organization", "PostsInput", "Post"]


def descobrir():
    info = {}
    for t in TIPOS:
        r = gql("""query($n:String!){__type(name:$n){name kind
          inputFields{name type{name kind ofType{name kind ofType{name kind ofType{name}}}}}
          fields{name type{name kind ofType{name kind ofType{name kind ofType{name}}}}}
          enumValues{name} possibleTypes{name}}}""", {"n": t})
        info.setdefault("tipos", {})[t] = r.get("data", r)
    orgs = gql("query{account{organizations{id name}}}")
    info["organizacoes"] = orgs
    canais = []
    for o in (orgs.get("data") or {}).get("account", {}).get("organizations", []) or []:
        r = gql("query($id:OrganizationId!){channels(input:{organizationId:$id}){id name service}}", {"id": o["id"]})
        if "errors" in r:
            r = gql("query($id:String!){channels(input:{organizationId:$id}){id name service}}", {"id": o["id"]})
        info.setdefault("canais_brutos", []).append(r)
        canais += (r.get("data") or {}).get("channels", []) or []
    info["canais"] = canais
    INFO.parent.mkdir(exist_ok=True)
    INFO.write_text(json.dumps(info, ensure_ascii=False, indent=1))
    print(json.dumps({"canais": canais, "orgs": orgs}, ensure_ascii=False)[:3000])


# ---------------- agendamento ----------------
import re, time, unicodedata
from datetime import datetime, timedelta, timezone

SITE = "https://radardeoferta.github.io/radar-de-ofertas"
FEITOS = BASE / "data" / "buffer_agendados.json"
BRT = timezone(timedelta(hours=-3))


def slug(txt):
    t = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:50]


def ler_posts():
    posts = []
    for bloco in re.split(r"\n\s*\n", (BASE / "series.txt").read_text(encoding="utf-8")):
        p = {}
        for linha in bloco.splitlines():
            if linha.strip().startswith("#") or ":" not in linha:
                continue
            k, v = (x.strip() for x in linha.split(":", 1))
            if k.upper() != "PRODUTO":
                p[k.lower()] = v
        if p.get("titulo") and p.get("data") and p.get("hora"):
            posts.append(p)
    return posts


def quando(p):
    d, m = (int(x) for x in re.search(r"(\d{1,2})/(\d{1,2})", p["data"]).groups())
    h = int(re.search(r"(\d{1,2})", p["hora"]).group(1))
    hoje = datetime.now(BRT)
    ano = hoje.year + (1 if m < hoje.month - 6 else 0)
    return datetime(ano, m, d, h, 0, tzinfo=BRT)


def canais():
    info = json.loads(INFO.read_text()) if INFO.exists() else {}
    cs = info.get("canais") or []
    if not cs:
        descobrir()
        cs = json.loads(INFO.read_text())["canais"]
    return {c["service"]: c["id"] for c in cs}


def pastas(pin_id):
    r = gql("query($id:ChannelId!){channel(input:{id:$id}){metadata{... on PinterestMetadata{boards{serviceId name}}}}}",
            {"id": pin_id})
    boards = (((r.get("data") or {}).get("channel") or {}).get("metadata") or {}).get("boards") or []
    if not boards:
        print("[aviso] pastas do Pinterest nao vieram:", str(r)[:400])
    return {b["name"].strip().lower(): b["serviceId"] for b in boards}


def esperar_url(url, limite=600):
    fim = time.time() + limite
    while time.time() < fim:
        try:
            urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20)
            return True
        except Exception:
            time.sleep(20)
    return False


def criar(channel, texto, imagens, meta, due):
    q = """mutation($i:CreatePostInput!){createPost(input:$i){
      ... on PostActionSuccess{post{id dueAt status}}
      ... on MutationError{message}}}"""
    i = {"channelId": channel, "text": texto, "assets": [{"image": {"url": u}} for u in imagens],
         "metadata": meta, "mode": "customScheduled", "dueAt": due, "schedulingType": "automatic",
         "needsApproval": False, "aiAssisted": True}
    return gql(q, {"i": i})


def agendar():
    ids = canais()
    feitos = json.loads(FEITOS.read_text()) if FEITOS.exists() else {}
    mapa_pastas = pastas(ids["pinterest"]) if "pinterest" in ids else {}
    agora = datetime.now(BRT)
    for p in ler_posts():
        s = slug(p["titulo"])
        due_dt = quando(p)
        if due_dt < agora + timedelta(minutes=20):
            continue
        pasta_png = BASE / "docs" / "series" / s
        n = len(list(pasta_png.glob("*.png")))
        if not n:
            print(f"[aviso] sem imagens para {s}")
            continue
        imgs = [f"{SITE}/series/{s}/{i:02d}.png" for i in range(1, n + 1)]
        if not esperar_url(imgs[-1]):
            print(f"[aviso] imagens ainda nao estao no site: {s}")
            continue
        due = due_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        texto = p.get("legenda", "").replace("\\n", "\n")
        reg = feitos.setdefault(s, {})
        if "instagram" in ids and not reg.get("instagram"):
            meta = {"instagram": {"type": "carousel" if n > 1 else "post", "shouldShareToFeed": True, "isAiGenerated": True}}
            r = criar(ids["instagram"], texto, imgs[:10], meta, due)
            ok = ((r.get("data") or {}).get("createPost") or {}).get("post")
            print("instagram", s, "OK" if ok else r)
            if ok:
                reg["instagram"] = ok["id"]
        if "pinterest" in ids and not reg.get("pinterest"):
            board = mapa_pastas.get(p.get("pasta", "").strip().lower())
            meta = {"pinterest": {"title": p.get("post", p["titulo"])[:100], "url": f"{SITE}/series/{s}/"}}
            if board:
                meta["pinterest"]["boardServiceId"] = board
            r = criar(ids["pinterest"], texto, imgs[:1], meta, due)
            ok = ((r.get("data") or {}).get("createPost") or {}).get("post")
            print("pinterest", s, "OK" if ok else r)
            if ok:
                reg["pinterest"] = ok["id"]
        FEITOS.write_text(json.dumps(feitos, ensure_ascii=False, indent=1))


def teste():
    ids = canais()
    print("canais:", ids)
    print("pastas do Pinterest:", pastas(ids["pinterest"]))
    r = gql("query($id:OrganizationId!){posts(input:{organizationId:$id,filter:{status:[scheduled]}}){edges{node{id dueAt channelService}}}}",
            {"id": json.loads(INFO.read_text())["organizacoes"]["data"]["account"]["organizations"][0]["id"]})
    print("agendados:", json.dumps(r)[:1500])


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "descobrir"
    {"descobrir": descobrir, "agendar": agendar, "teste": teste}.get(modo, descobrir)()
