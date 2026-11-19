# -*- coding: utf-8 -*-
"""Imagens e sons enviados pelo editor, e copia de seguranca (exportar/importar zip)."""
import json
import os
import re
import tempfile
import time
import zipfile

from . import paths, schema, storage

MAX_IMAGE = 2 * 1024 * 1024
MAX_SOUND = 20 * 1024 * 1024
MAX_IMPORT = 200 * 1024 * 1024
MAX_IMPORT_TOTAL = 600 * 1024 * 1024     # soma descompactada
MAX_IMPORT_FILES = 2000

IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".gif": "image/gif", ".webp": "image/webp"}
SOUND_PART_RE = re.compile(r"^[A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ ._()\-]{0,99}$")


def image_type(data):
    """Extensao pelo conteudo (bytes magicos) ou None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def clean_name(name, ext):
    """Nome seguro (so o nome do arquivo, caracteres simples) com a extensao ext."""
    base = os.path.basename(str(name or "").replace("\\", "/"))
    stem = os.path.splitext(base)[0]
    stem = re.sub(r"[^A-Za-z0-9 ._()\-]", "_", stem)
    # o nome precisa comecar com letra ou digito ('-logo', '(1) foto')
    stem = re.sub(r"^[^A-Za-z0-9]+", "", stem).rstrip(" ._")[:80].rstrip(" ._") or "arquivo"
    return stem + ext


def _unique(folder, name):
    stem, ext = os.path.splitext(name)
    out, n = name, 2
    while os.path.exists(os.path.join(folder, out)):
        out = "%s-%d%s" % (stem, n, ext)
        n += 1
    return out


def _write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def save_image(name, data):
    if not data:
        raise ValueError("arquivo vazio")
    if len(data) > MAX_IMAGE:
        raise ValueError("imagem grande demais (maximo 2 MB)")
    ext = image_type(data)
    if not ext:
        raise ValueError("formato de imagem nao aceito (use PNG, JPG, GIF ou WEBP)")
    os.makedirs(paths.IMAGES_DIR, exist_ok=True)
    final = _unique(paths.IMAGES_DIR, clean_name(name, ext))
    if not schema.safe_image_name(final):
        raise ValueError("nome invalido")
    _write(os.path.join(paths.IMAGES_DIR, final), data)
    return final


def save_sound(name, data):
    ext = os.path.splitext(str(name or ""))[1].lower()
    if ext not in paths.SOUND_EXT:
        raise ValueError("formato de som nao aceito (use MP3, WAV, WMA ou M4A)")
    if not data:
        raise ValueError("arquivo vazio")
    if len(data) > MAX_SOUND:
        raise ValueError("som grande demais (maximo 20 MB)")
    os.makedirs(paths.SOUNDS_DIR, exist_ok=True)
    final = _unique(paths.SOUNDS_DIR, clean_name(name, ext))
    _write(os.path.join(paths.SOUNDS_DIR, final), data)
    return final


def list_images():
    if not os.path.isdir(paths.IMAGES_DIR):
        return []
    return sorted([f for f in os.listdir(paths.IMAGES_DIR)
                   if f.lower().endswith(paths.IMAGE_EXT) and schema.safe_image_name(f)
                   and os.path.isfile(os.path.join(paths.IMAGES_DIR, f))], key=str.lower)


def image_file(name):
    """(caminho, mime) de uma imagem de imagens/ ou None."""
    if not schema.safe_image_name(name):
        return None
    ext = os.path.splitext(name)[1].lower()
    if ext not in IMAGE_MIME:
        return None
    full = os.path.join(paths.IMAGES_DIR, name)
    if not paths.inside(full, paths.IMAGES_DIR) or not os.path.isfile(full):
        return None
    return full, IMAGE_MIME[ext]


# ------------------------------------------------------------ exportar ---
def export_zip():
    """Arquivo temporario (aberto, no inicio) com o zip e o nome sugerido."""
    tmp = tempfile.TemporaryFile()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.isfile(paths.CONFIG_PATH):
            z.write(paths.CONFIG_PATH, "config.json")
        for folder, prefix in ((paths.IMAGES_DIR, "imagens"), (paths.SOUNDS_DIR, "sons")):
            if not os.path.isdir(folder):
                continue
            for root, _dirs, files in os.walk(folder):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, folder).replace("\\", "/")
                    if f.endswith(".tmp") or not paths.inside(full, folder):
                        continue
                    z.write(full, "%s/%s" % (prefix, rel))
    tmp.seek(0)
    return tmp, "streamdeck-backup-%s.zip" % time.strftime("%Y%m%d")


# ------------------------------------------------------------ importar ---
def _safe_member(name):
    """('imagens'|'sons', partes) para um item aceitavel do zip, senao None."""
    n = name.replace("\\", "/")
    if n.startswith("/") or ":" in n:
        return None
    parts = n.split("/")
    if len(parts) < 2 or parts[0] not in ("imagens", "sons") or not parts[-1]:
        return None
    rest = parts[1:]
    if any(p in ("", ".", "..") for p in rest):
        return None
    if parts[0] == "imagens":
        if len(rest) != 1 or not schema.safe_image_name(rest[0]) \
                or not rest[0].lower().endswith(paths.IMAGE_EXT):
            return None
    else:
        if len(rest) > 3 or not all(SOUND_PART_RE.match(p) for p in rest) \
                or not rest[-1].lower().endswith(paths.SOUND_EXT):
            return None
    return parts[0], rest


def import_zip(fileobj):
    """Confere o zip inteiro, depois grava imagens/sons e troca o config
    (o anterior fica em config.bak.json). Devolve (n imagens, n sons)."""
    if not hasattr(fileobj, "seekable"):
        # SpooledTemporaryFile so tem seekable() a partir do Python 3.11
        import tempfile, shutil
        tmp = tempfile.TemporaryFile()
        fileobj.seek(0)
        shutil.copyfileobj(fileobj, tmp)
        tmp.seek(0)
        fileobj = tmp
    try:
        z = zipfile.ZipFile(fileobj)
    except zipfile.BadZipFile:
        raise ValueError("arquivo nao e um zip valido")
    with z:
        infos = z.infolist()
        if len(infos) > MAX_IMPORT_FILES:
            raise ValueError("arquivos demais no zip")
        if sum(i.file_size for i in infos) > MAX_IMPORT_TOTAL:
            raise ValueError("zip grande demais")
        try:
            info = z.getinfo("config.json")
        except KeyError:
            raise ValueError("o zip nao tem config.json")
        if info.file_size > 2000000:
            raise ValueError("config.json grande demais")
        cfg = json.loads(z.read(info).decode("utf-8-sig"))
        cfg, _ = schema.migrate(cfg)
        schema.validate_config(cfg)

        todo, skipped = [], 0
        for i in infos:
            if i.is_dir() or i.filename == "config.json":
                continue
            m = _safe_member(i.filename)
            limit = MAX_IMAGE if m and m[0] == "imagens" else MAX_SOUND
            if not m or i.file_size > limit:
                skipped += 1
                continue
            todo.append((i, m))
        n_img = n_snd = 0
        for i, (kind, rest) in todo:
            data = z.read(i)
            if len(data) > (MAX_IMAGE if kind == "imagens" else MAX_SOUND):
                skipped += 1
                continue
            if kind == "imagens":
                if not image_type(data):
                    skipped += 1
                    continue
                folder = paths.IMAGES_DIR
            else:
                folder = paths.SOUNDS_DIR
            dest = os.path.join(folder, *rest)
            if not paths.inside(dest, folder):
                skipped += 1
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            _write(dest, data)
            if kind == "imagens":
                n_img += 1
            else:
                n_snd += 1
        storage.save_config(cfg)
        if skipped:
            print("  importar: %d arquivo(s) ignorado(s)" % skipped)
        return n_img, n_snd
