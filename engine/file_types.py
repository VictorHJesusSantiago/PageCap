"""
Complete registry of file types PageCap can detect, download, and convert.
Each entry maps extension → FileTypeInfo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileTypeInfo:
    ext: str                        # canonical extension (with dot)
    mime: str                       # primary MIME type
    label: str                      # human-readable name
    category: str                   # top-level category
    aliases: list[str] = field(default_factory=list)   # alternative extensions
    can_convert_to: list[str] = field(default_factory=list)  # target extensions


# ─── Registry ────────────────────────────────────────────────────────────────
REGISTRY: dict[str, FileTypeInfo] = {}

def _r(info: FileTypeInfo):
    REGISTRY[info.ext] = info
    for alias in info.aliases:
        REGISTRY[alias] = info

# ── Text / Documents ──────────────────────────────────────────────────────────
_r(FileTypeInfo(".txt",  "text/plain",           "Texto puro",           "text",
    can_convert_to=[".md", ".html", ".pdf", ".docx", ".odt", ".rtf", ".epub"]))
_r(FileTypeInfo(".md",   "text/markdown",        "Markdown",             "text",
    aliases=[".markdown"],
    can_convert_to=[".html", ".pdf", ".docx", ".odt", ".rtf", ".epub", ".txt"]))
_r(FileTypeInfo(".rtf",  "application/rtf",      "Rich Text Format",     "text",
    can_convert_to=[".docx", ".odt", ".pdf", ".txt", ".html"]))
_r(FileTypeInfo(".doc",  "application/msword",   "Word (legado)",        "text",
    can_convert_to=[".docx", ".pdf", ".odt", ".html", ".txt", ".rtf", ".epub"]))
_r(FileTypeInfo(".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "Word (moderno)", "text",
    can_convert_to=[".pdf", ".odt", ".html", ".txt", ".rtf", ".epub", ".md"]))
_r(FileTypeInfo(".odt",  "application/vnd.oasis.opendocument.text", "OpenDocument Text", "text",
    can_convert_to=[".docx", ".pdf", ".html", ".txt", ".rtf", ".epub"]))
_r(FileTypeInfo(".pdf",  "application/pdf",      "PDF",                  "text",
    can_convert_to=[".html", ".txt", ".docx"]))
_r(FileTypeInfo(".tex",  "application/x-tex",    "LaTeX",                "text",
    can_convert_to=[".pdf", ".html", ".docx"]))
_r(FileTypeInfo(".epub", "application/epub+zip", "ePub",                 "text",
    can_convert_to=[".pdf", ".html", ".txt", ".docx", ".mobi"]))
_r(FileTypeInfo(".mobi", "application/x-mobipocket-ebook", "MOBI",       "text",
    can_convert_to=[".epub", ".pdf"]))
_r(FileTypeInfo(".pages","application/x-iwork-pages-sffpages","Apple Pages","text"))
_r(FileTypeInfo(".log",  "text/plain",           "Log",                  "text"))

# ── Spreadsheets ─────────────────────────────────────────────────────────────
_r(FileTypeInfo(".csv",  "text/csv",             "CSV",                  "spreadsheet",
    can_convert_to=[".xlsx", ".ods", ".json", ".parquet", ".tsv", ".html"]))
_r(FileTypeInfo(".tsv",  "text/tab-separated-values", "TSV",             "spreadsheet",
    can_convert_to=[".csv", ".xlsx", ".json"]))
_r(FileTypeInfo(".xls",  "application/vnd.ms-excel", "Excel (legado)",   "spreadsheet",
    can_convert_to=[".xlsx", ".csv", ".ods", ".json", ".parquet"]))
_r(FileTypeInfo(".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "Excel (moderno)", "spreadsheet",
    can_convert_to=[".csv", ".ods", ".json", ".parquet", ".html", ".xls"]))
_r(FileTypeInfo(".ods",  "application/vnd.oasis.opendocument.spreadsheet","OpenDocument Spreadsheet","spreadsheet",
    can_convert_to=[".xlsx", ".csv", ".json"]))
_r(FileTypeInfo(".numbers","application/x-iwork-numbers-sffnumbers","Apple Numbers","spreadsheet"))

# ── Presentations ─────────────────────────────────────────────────────────────
_r(FileTypeInfo(".ppt",  "application/vnd.ms-powerpoint", "PowerPoint (legado)", "presentation",
    can_convert_to=[".pptx", ".pdf", ".odp"]))
_r(FileTypeInfo(".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "PowerPoint (moderno)", "presentation",
    can_convert_to=[".pdf", ".odp", ".html"]))
_r(FileTypeInfo(".odp",  "application/vnd.oasis.opendocument.presentation","OpenDocument Presentation","presentation",
    can_convert_to=[".pptx", ".pdf"]))
_r(FileTypeInfo(".key",  "application/x-iwork-keynote-sffkey", "Apple Keynote", "presentation"))

# ── Raster Images ─────────────────────────────────────────────────────────────
_img = [".jpg",".jpeg",".png",".gif",".bmp",".webp",".tiff",".tif",".avif",".heic",".heif",".ico"]
_r(FileTypeInfo(".jpg",  "image/jpeg",  "JPEG",   "image", aliases=[".jpeg"],
    can_convert_to=[x for x in _img if x not in (".jpg",".jpeg")]+[".pdf",".webp",".avif"]))
_r(FileTypeInfo(".png",  "image/png",   "PNG",    "image",
    can_convert_to=[x for x in _img if x != ".png"]+[".pdf",".svg"]))
_r(FileTypeInfo(".gif",  "image/gif",   "GIF",    "image",
    can_convert_to=[".mp4",".webm",".apng",".png",".jpg"]))
_r(FileTypeInfo(".bmp",  "image/bmp",   "Bitmap", "image",
    can_convert_to=[".jpg",".png",".webp"]))
_r(FileTypeInfo(".webp", "image/webp",  "WebP",   "image",
    can_convert_to=[".jpg",".png",".avif",".gif"]))
_r(FileTypeInfo(".tiff", "image/tiff",  "TIFF",   "image", aliases=[".tif"],
    can_convert_to=[".jpg",".png",".pdf",".webp"]))
_r(FileTypeInfo(".ico",  "image/x-icon","ICO",    "image",
    can_convert_to=[".png"]))
_r(FileTypeInfo(".avif", "image/avif",  "AVIF",   "image",
    can_convert_to=[".jpg",".png",".webp"]))
_r(FileTypeInfo(".heic", "image/heic",  "HEIC",   "image", aliases=[".heif"],
    can_convert_to=[".jpg",".png",".webp"]))
_r(FileTypeInfo(".psd",  "image/vnd.adobe.photoshop","Photoshop","image",
    can_convert_to=[".png",".jpg",".pdf"]))
_r(FileTypeInfo(".raw",  "image/x-raw", "RAW (câmera)", "image",
    aliases=[".cr2",".nef",".arw",".dng",".orf",".rw2"],
    can_convert_to=[".jpg",".png",".tiff"]))
_r(FileTypeInfo(".xcf",  "image/x-xcf", "GIMP XCF","image",
    can_convert_to=[".png",".jpg"]))

# ── Vector Images ─────────────────────────────────────────────────────────────
_r(FileTypeInfo(".svg",  "image/svg+xml","SVG",   "vector",
    can_convert_to=[".png",".pdf",".jpg",".eps"]))
_r(FileTypeInfo(".eps",  "application/postscript","EPS","vector",
    can_convert_to=[".pdf",".png",".svg"]))
_r(FileTypeInfo(".ai",   "application/postscript","Adobe Illustrator","vector",
    can_convert_to=[".svg",".pdf",".png"]))
_r(FileTypeInfo(".wmf",  "image/wmf",   "WMF/EMF","vector", aliases=[".emf"],
    can_convert_to=[".png",".svg"]))
_r(FileTypeInfo(".sketch","application/octet-stream","Sketch","vector"))

# ── Audio ─────────────────────────────────────────────────────────────────────
_aud = [".mp3",".wav",".ogg",".flac",".aac",".m4a",".wma",".opus",".aiff",".aif"]
_r(FileTypeInfo(".mp3",  "audio/mpeg",      "MP3",     "audio",
    can_convert_to=[x for x in _aud if x != ".mp3"]))
_r(FileTypeInfo(".wav",  "audio/wav",       "WAV",     "audio",
    can_convert_to=[x for x in _aud if x != ".wav"]))
_r(FileTypeInfo(".ogg",  "audio/ogg",       "OGG",     "audio",
    can_convert_to=[x for x in _aud if x != ".ogg"]))
_r(FileTypeInfo(".flac", "audio/flac",      "FLAC",    "audio",
    can_convert_to=[x for x in _aud if x != ".flac"]))
_r(FileTypeInfo(".aac",  "audio/aac",       "AAC",     "audio",
    can_convert_to=[x for x in _aud if x != ".aac"]))
_r(FileTypeInfo(".m4a",  "audio/m4a",       "M4A",     "audio",
    can_convert_to=[x for x in _aud if x != ".m4a"]))
_r(FileTypeInfo(".wma",  "audio/x-ms-wma",  "WMA",     "audio",
    can_convert_to=[x for x in _aud if x != ".wma"]))
_r(FileTypeInfo(".opus", "audio/opus",      "Opus",    "audio",
    can_convert_to=[x for x in _aud if x != ".opus"]))
_r(FileTypeInfo(".aiff", "audio/aiff",      "AIFF",    "audio", aliases=[".aif"],
    can_convert_to=[x for x in _aud if x not in (".aiff",".aif")]))
_r(FileTypeInfo(".mid",  "audio/midi",      "MIDI",    "audio", aliases=[".midi"]))
_r(FileTypeInfo(".ra",   "audio/x-realaudio","RealAudio","audio"))

# ── Video ─────────────────────────────────────────────────────────────────────
_vid = [".mp4",".avi",".mkv",".mov",".wmv",".webm",".ogv",".3gp",".ts",".flv"]
_r(FileTypeInfo(".mp4",  "video/mp4",        "MPEG-4",    "video", aliases=[".m4v"],
    can_convert_to=[x for x in _vid if x != ".mp4"]+[".mp3",".gif"]))
_r(FileTypeInfo(".avi",  "video/x-msvideo",  "AVI",       "video",
    can_convert_to=[x for x in _vid if x != ".avi"]))
_r(FileTypeInfo(".mkv",  "video/x-matroska", "Matroska",  "video",
    can_convert_to=[x for x in _vid if x != ".mkv"]))
_r(FileTypeInfo(".mov",  "video/quicktime",  "QuickTime", "video",
    can_convert_to=[x for x in _vid if x != ".mov"]))
_r(FileTypeInfo(".wmv",  "video/x-ms-wmv",   "WMV",       "video",
    can_convert_to=[x for x in _vid if x != ".wmv"]))
_r(FileTypeInfo(".flv",  "video/x-flv",      "Flash Video","video", aliases=[".f4v"],
    can_convert_to=[x for x in _vid if x != ".flv"]))
_r(FileTypeInfo(".webm", "video/webm",        "WebM",      "video",
    can_convert_to=[x for x in _vid if x != ".webm"]))
_r(FileTypeInfo(".ogv",  "video/ogg",         "OGG Video", "video",
    can_convert_to=[x for x in _vid if x != ".ogv"]))
_r(FileTypeInfo(".3gp",  "video/3gpp",        "3GPP",      "video",
    can_convert_to=[x for x in _vid if x != ".3gp"]))
_r(FileTypeInfo(".ts",   "video/mp2t",        "MPEG-TS",   "video", aliases=[".m2ts"],
    can_convert_to=[".mp4",".mkv"]))
_r(FileTypeInfo(".vob",  "video/dvd",         "VOB (DVD)", "video",
    can_convert_to=[".mp4",".mkv"]))
_r(FileTypeInfo(".rm",   "application/vnd.rn-realmedia","RealMedia","video", aliases=[".rmvb"]))

# ── Code ──────────────────────────────────────────────────────────────────────
_code = {
    ".html": ("text/html","HTML"), ".htm": ("text/html","HTML"),
    ".css":  ("text/css","CSS"),
    ".js":   ("text/javascript","JavaScript"), ".mjs": ("text/javascript","JS Module"),
    ".ts":   ("text/typescript","TypeScript"),
    ".jsx":  ("text/jsx","JSX"), ".tsx": ("text/tsx","TSX"),
    ".json": ("application/json","JSON"),
    ".xml":  ("application/xml","XML"),
    ".wasm": ("application/wasm","WebAssembly"),
    ".php":  ("text/x-php","PHP"),
    ".py":   ("text/x-python","Python"),
    ".java": ("text/x-java-source","Java"),
    ".cs":   ("text/x-csharp","C#"),
    ".cpp":  ("text/x-c++src","C++"), ".cc": ("text/x-c++src","C++"), ".cxx": ("text/x-c++src","C++"),
    ".c":    ("text/x-csrc","C"),
    ".go":   ("text/x-go","Go"),
    ".rs":   ("text/x-rustsrc","Rust"),
    ".rb":   ("text/x-ruby","Ruby"),
    ".swift":("text/x-swift","Swift"),
    ".kt":   ("text/x-kotlin","Kotlin"),
    ".r":    ("text/x-rsrc","R"),
    ".sql":  ("text/x-sql","SQL"),
    ".sh":   ("text/x-shellscript","Shell"), ".bash": ("text/x-shellscript","Bash"),
    ".bat":  ("text/x-msdos-batch","Batch"), ".cmd": ("text/x-msdos-batch","CMD"),
    ".ps1":  ("text/x-powershell","PowerShell"),
    ".lua":  ("text/x-lua","Lua"),
    ".dart": ("application/dart","Dart"),
    ".vue":  ("text/x-vue","Vue SFC"),
    ".svelte":("text/x-svelte","Svelte"),
    ".scala":("text/x-scala","Scala"),
    ".pl":   ("text/x-perl","Perl"),
}
for _ext, (_mime, _label) in _code.items():
    _r(FileTypeInfo(_ext, _mime, _label, "code",
        can_convert_to=[".html", ".pdf", ".txt"] if _ext not in (".html",".htm") else [".pdf",".txt"]))

# ── Executables / Binaries ────────────────────────────────────────────────────
for _ext, _mime, _label in [
    (".exe","application/x-msdownload","Executável Windows"),
    (".msi","application/x-msi","Instalador Windows"),
    (".apk","application/vnd.android.package-archive","APK Android"),
    (".aab","application/octet-stream","AAB Android"),
    (".ipa","application/octet-stream","IPA iOS"),
    (".dmg","application/x-apple-diskimage","DMG macOS"),
    (".deb","application/vnd.debian.binary-package","DEB Linux"),
    (".rpm","application/x-rpm","RPM Linux"),
    (".AppImage","application/octet-stream","AppImage Linux"),
    (".jar","application/java-archive","JAR Java"),
    (".war","application/java-archive","WAR Java"),
    (".dll","application/x-msdownload","DLL Windows"),
    (".so", "application/x-sharedlib","SO Linux"),
    (".dylib","application/x-mach-binary","dylib macOS"),
    (".pyc","application/x-python-bytecode","Python Bytecode"),
    (".class","application/java-vm","Java Class"),
    (".bin","application/octet-stream","Binário genérico"),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "executable"))

# ── Archives / Compression ────────────────────────────────────────────────────
_arc = [".zip",".rar",".7z",".tar",".tar.gz",".tgz",".tar.bz2",".tbz2",".tar.xz",".txz",
        ".gz",".bz2",".xz",".zst",".br",".cab",".iso",".img"]
for _ext, _mime, _label in [
    (".zip","application/zip","ZIP"),
    (".rar","application/x-rar-compressed","RAR"),
    (".7z", "application/x-7z-compressed","7-Zip"),
    (".tar","application/x-tar","TAR"),
    (".tar.gz","application/x-compressed-tar","TAR+Gzip"), (".tgz","application/x-compressed-tar","TGZ"),
    (".tar.bz2","application/x-bz2-compressed-tar","TAR+Bzip2"), (".tbz2","application/x-bz2-compressed-tar","TBZ2"),
    (".tar.xz","application/x-xz-compressed-tar","TAR+XZ"), (".txz","application/x-xz-compressed-tar","TXZ"),
    (".gz","application/gzip","Gzip"),
    (".bz2","application/x-bzip2","Bzip2"),
    (".xz","application/x-xz","XZ"),
    (".zst","application/zstd","Zstandard"),
    (".br","application/x-br","Brotli"),
    (".cab","application/vnd.ms-cab-compressed","CAB"),
    (".iso","application/x-iso9660-image","ISO"),
    (".img","application/octet-stream","IMG"),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "archive",
        can_convert_to=[".zip"] if _ext not in (".zip",".iso",".img") else []))

# ── Data / Databases ─────────────────────────────────────────────────────────
for _ext, _mime, _label, _to in [
    (".sqlite","application/vnd.sqlite3","SQLite",[".csv",".json"]),
    (".sqlite3","application/vnd.sqlite3","SQLite3",[".csv",".json"]),
    (".db","application/vnd.sqlite3","Database",[".csv",".json"]),
    (".parquet","application/octet-stream","Parquet",[".csv",".json",".xlsx",".arrow"]),
    (".avro","application/octet-stream","Avro",[".json",".parquet"]),
    (".orc","application/octet-stream","ORC",[".parquet",".csv"]),
    (".h5","application/x-hdf","HDF5",[".json",".csv"]),
    (".hdf5","application/x-hdf","HDF5",[".json",".csv"]),
    (".arrow","application/octet-stream","Arrow",[".parquet",".csv",".json"]),
    (".feather","application/octet-stream","Feather",[".parquet",".csv",".json"]),
    (".ndjson","application/x-ndjson","NDJSON",[".json",".csv"]),
    (".jsonl","application/x-ndjson","JSONL",[".json",".csv"]),
    (".proto","text/plain","Protobuf schema",[]),
    (".msgpack","application/x-msgpack","MessagePack",[".json"]),
    (".cbor","application/cbor","CBOR",[".json"]),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "data", can_convert_to=_to))

# ── Fonts ─────────────────────────────────────────────────────────────────────
for _ext, _mime, _label, _to in [
    (".ttf","font/ttf","TrueType",[".otf",".woff",".woff2"]),
    (".otf","font/otf","OpenType",[".ttf",".woff",".woff2"]),
    (".woff","font/woff","WOFF",[".ttf",".otf",".woff2"]),
    (".woff2","font/woff2","WOFF2",[".ttf",".otf",".woff"]),
    (".eot","application/vnd.ms-fontobject","EOT",[".ttf",".woff"]),
    (".pfb","application/x-font","PostScript Font",[".ttf",".otf"]),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "font", can_convert_to=_to))

# ── 3D Models ─────────────────────────────────────────────────────────────────
for _ext, _mime, _label, _to in [
    (".obj","model/obj","Wavefront OBJ",[".stl",".gltf",".glb"]),
    (".fbx","application/octet-stream","FBX",[".gltf",".obj",".stl"]),
    (".stl","model/stl","STL",[".obj",".gltf"]),
    (".gltf","model/gltf+json","glTF",[".glb",".obj"]),
    (".glb","model/gltf-binary","GLB",[".gltf",".obj"]),
    (".dae","model/vnd.collada+xml","Collada",[".gltf",".obj"]),
    (".blend","application/x-blender","Blender",[]),
    (".usdz","model/vnd.usdz+zip","USDZ",[]),
    (".3ds","application/x-3ds","3DS",[".obj",".gltf"]),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "3d", can_convert_to=_to))

# ── Certificates / Crypto ─────────────────────────────────────────────────────
for _ext, _mime, _label in [
    (".pem","application/x-pem-file","PEM"),
    (".crt","application/x-x509-ca-cert","Certificado X.509"),
    (".cer","application/x-x509-ca-cert","CER"),
    (".key","application/pkcs8","Chave privada"),
    (".pfx","application/x-pkcs12","PKCS#12"), (".p12","application/x-pkcs12","P12"),
    (".pub","text/plain","Chave pública"),
    (".csr","application/pkcs10","CSR"),
    (".jks","application/x-java-keystore","JKS"),
    (".p7b","application/pkcs7-mime","PKCS#7"), (".p7c","application/pkcs7-mime","P7C"),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "certificate"))

# ── Subtitles ─────────────────────────────────────────────────────────────────
for _ext, _mime, _label, _to in [
    (".srt","text/plain","SubRip",[".vtt",".ass",".ttml"]),
    (".vtt","text/vtt","WebVTT",[".srt",".ass"]),
    (".ass","text/x-ass","ASS/SSA",[".srt",".vtt"]), (".ssa","text/x-ass","SSA",[".srt"]),
    (".sub","text/plain","SUB",[".srt"]),
    (".ttml","application/ttml+xml","TTML",[".srt",".vtt"]),
    (".lrc","text/plain","LRC",[".srt"]),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "subtitle", can_convert_to=_to))

# ── ML / AI Models ────────────────────────────────────────────────────────────
for _ext, _mime, _label in [
    (".onnx","application/octet-stream","ONNX"),
    (".pt","application/octet-stream","PyTorch"), (".pth","application/octet-stream","PyTorch"),
    (".keras","application/x-hdf","Keras"),
    (".pb","application/octet-stream","TF Protocol Buffer"),
    (".gguf","application/octet-stream","GGUF"),
    (".ggml","application/octet-stream","GGML"),
    (".safetensors","application/octet-stream","SafeTensors"),
    (".pkl","application/octet-stream","Pickle"),
    (".joblib","application/octet-stream","Joblib"),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "ml"))

# ── Config ────────────────────────────────────────────────────────────────────
for _ext, _mime, _label, _to in [
    (".ini","text/plain","INI",[".toml",".yaml",".json"]),
    (".cfg","text/plain","Config",[".toml",".yaml",".json"]),
    (".conf","text/plain","Conf",[".toml",".yaml"]),
    (".env","text/plain","Env vars",[]),
    (".yaml","text/yaml","YAML",[".json",".toml"]), (".yml","text/yaml","YAML",[".json",".toml"]),
    (".toml","text/toml","TOML",[".json",".yaml"]),
    (".gitignore","text/plain","Gitignore",[]),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "config", can_convert_to=_to))

# ── Build / System ────────────────────────────────────────────────────────────
for _ext, _mime, _label in [
    (".dockerfile","text/plain","Dockerfile"),
    (".lock","text/plain","Lock file"),
    (".csproj","text/xml","C# Project"), (".sln","text/xml","Solution"),
    (".gradle","text/plain","Gradle"), (".kts","text/plain","Kotlin Script"),
    (".htaccess","text/plain",".htaccess"),
    (".makefile","text/plain","Makefile"),
    (".editorconfig","text/plain","EditorConfig"),
]:
    _r(FileTypeInfo(_ext, _mime, _label, "config"))


# ─── Helpers ─────────────────────────────────────────────────────────────────

ALL_EXTENSIONS: frozenset[str] = frozenset(REGISTRY.keys())

# MIME → list[ext] lookup
MIME_TO_EXTS: dict[str, list[str]] = {}
for _ext, _info in REGISTRY.items():
    MIME_TO_EXTS.setdefault(_info.mime, []).append(_ext)


def get_info(ext_or_mime: str) -> Optional[FileTypeInfo]:
    """Look up FileTypeInfo by extension (with dot) or MIME type."""
    if ext_or_mime in REGISTRY:
        return REGISTRY[ext_or_mime]
    for _ext, info in REGISTRY.items():
        if info.mime == ext_or_mime:
            return info
    return None


def category_of(ext: str) -> str:
    info = REGISTRY.get(ext.lower())
    return info.category if info else "other"


def mime_of(ext: str) -> str:
    info = REGISTRY.get(ext.lower())
    return info.mime if info else "application/octet-stream"


def conversions_for(ext: str) -> list[str]:
    info = REGISTRY.get(ext.lower())
    return info.can_convert_to if info else []


def all_in_category(cat: str) -> list[FileTypeInfo]:
    seen = set()
    result = []
    for info in REGISTRY.values():
        if info.category == cat and info.ext not in seen:
            seen.add(info.ext)
            result.append(info)
    return result


def categories() -> list[str]:
    return sorted({i.category for i in REGISTRY.values()})
