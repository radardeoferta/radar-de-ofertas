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


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "descobrir"
    {"descobrir": descobrir}.get(modo, descobrir)()
