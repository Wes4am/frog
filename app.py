import json
import re
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag
import streamlit.components.v1 as components
import html
import requests
import streamlit as st
from bs4 import BeautifulSoup

UA = "SimpleFlowCrawler/0.1"

def normalize_url(base: str, href: str) -> str | None:
    if href is None:
        return None
    href = href.strip()

    if href.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None

    abs_url = urljoin(base, href)
    abs_url, _ = urldefrag(abs_url)

    p = urlparse(abs_url)
    if p.scheme not in ("http", "https"):
        return None

    netloc = p.netloc
    if netloc.endswith(":80") and p.scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and p.scheme == "https":
        netloc = netloc[:-4]

    path = re.sub(r"/{2,}", "/", p.path or "/")
    return p._replace(netloc=netloc, path=path).geturl()

def is_internal(url: str, root_netloc: str) -> bool:
    try:
        return urlparse(url).netloc == root_netloc
    except Exception:
        return False

def fetch_html(url: str, timeout: int = 15):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
        ct = (r.headers.get("Content-Type") or "").lower()
        if "text/html" not in ct:
            return r.status_code, None
        return r.status_code, r.text
    except Exception:
        return None, None

def extract_links(page_url: str, html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    out = set()
    for a in soup.find_all("a", href=True):
        u = normalize_url(page_url, a.get("href"))
        if u:
            out.add(u)
    return out

def build_mermaid(nodes: list[str], edges: list[tuple[str, str]]) -> str:
    id_map = {u: f"N{i}" for i, u in enumerate(nodes, start=1)}
    lines = ["flowchart TD"]
    for u in nodes:
        lines.append(f'  {id_map[u]}["{u.replace(chr(34), r"\"")}"]')
    for a, b in edges:
        if a in id_map and b in id_map:
            lines.append(f"  {id_map[a]} --> {id_map[b]}")
    return "\n".join(lines) + "\n"

def crawl(seed: str, max_pages: int, max_depth: int):
    seed = normalize_url(seed, "") or seed
    root_netloc = urlparse(seed).netloc

    q = deque([(seed, 0)])
    visited = set()
    edges = set()
    status_by_url = {}

    while q and len(visited) < max_pages:
        url, depth = q.popleft()
        if url in visited:
            continue
        visited.add(url)

        status, html = fetch_html(url)
        status_by_url[url] = status

        if not html or depth >= max_depth:
            continue

        for link in extract_links(url, html):
            if not is_internal(link, root_netloc):
                continue
            edges.add((url, link))
            if link not in visited:
                q.append((link, depth + 1))

    nodes = sorted(visited)
    edges_list = sorted(edges)
    data = {
        "seed": seed,
        "nodes": [{"url": u, "status": status_by_url.get(u)} for u in nodes],
        "edges": [{"from": a, "to": b} for a, b in edges_list],
    }
    mmd = build_mermaid(nodes, edges_list)
    return data, mmd

def render_mermaid(mermaid_code: str, height: int = 700):
    code_json = json.dumps(mermaid_code)

    html_content = f"""
    <div id="mermaid-container"></div>
    <button id="download-btn" style="margin-top: 10px; padding: 8px 16px; background-color: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer;">
        ⬇️ Download as PNG
    </button>

    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>
    (function() {{
        const code = {code_json};
        mermaid.initialize({{
        startOnLoad: false,
        securityLevel: "loose"
        }});

        const container = document.getElementById("mermaid-container");
        container.innerHTML = "";

        try {{
        mermaid.render("mermaid-svg", code).then(({{
            svg
        }}) => {{
            container.innerHTML = svg;
            
            // Add download functionality
            document.getElementById("download-btn").addEventListener("click", function() {{
                const svgElement = container.querySelector("svg");
                if (!svgElement) return;
                
                const svgData = new XMLSerializer().serializeToString(svgElement);
                const canvas = document.createElement("canvas");
                const ctx = canvas.getContext("2d");
                const img = new Image();
                
                const svgBlob = new Blob([svgData], {{type: "image/svg+xml;charset=utf-8"}});
                const url = URL.createObjectURL(svgBlob);
                
                img.onload = function() {{
                    canvas.width = img.width;
                    canvas.height = img.height;
                    ctx.fillStyle = "white";
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    ctx.drawImage(img, 0, 0);
                    
                    canvas.toBlob(function(blob) {{
                        const link = document.createElement("a");
                        link.download = "site-flow-diagram.png";
                        link.href = URL.createObjectURL(blob);
                        link.click();
                        URL.revokeObjectURL(url);
                    }});
                }};
                
                img.src = url;
            }});
        }}).catch((err) => {{
            container.innerHTML = "<pre style='color:red;white-space:pre-wrap;'>" + err + "</pre>";
        }});
        }} catch (e) {{
        container.innerHTML = "<pre style='color:red;white-space:pre-wrap;'>" + e + "</pre>";
        }}
    }})();
    </script>
    """
    components.html(html_content, height=height, scrolling=True)

st.set_page_config(page_title="Website Flow Crawler", layout="wide")

st.title("🕷️ Website Flow Crawler (Simple Screaming Frog-lite)")
st.caption("Enter a website → Crawl internal pages → Visual flowchart (Mermaid).")

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    seed = st.text_input("Seed URL", value="https://example.com")
with col2:
    max_pages = st.number_input("Max pages", min_value=1, max_value=5000, value=200, step=50)
with col3:
    max_depth = st.number_input("Max depth", min_value=0, max_value=20, value=3, step=1)

run = st.button("🚀 Crawl & Build Flowchart", use_container_width=True)

if run:
    if not seed.startswith(("http://", "https://")):
        st.error("Please include http:// or https:// in the URL.")
        st.stop()

    with st.spinner("Crawling..."):
        data, mmd = crawl(seed, int(max_pages), int(max_depth))

    left, right = st.columns([1, 1])

    with left:
        st.subheader("📌 Summary")
        st.write(f"**Seed:** {data['seed']}")
        st.write(f"**Pages found:** {len(data['nodes'])}")
        st.write(f"**Links found:** {len(data['edges'])}")

        st.download_button(
            "⬇️ Download crawl.json",
            data=json.dumps(data, indent=2, ensure_ascii=False),
            file_name="crawl.json",
            mime="application/json",
            use_container_width=True,
        )

    with right:
        st.subheader("📄 Mermaid Code")
        
        st.download_button(
            "⬇️ Download graph.mmd",
            data=mmd,
            file_name="graph.mmd",
            mime="text/plain",
            use_container_width=True,
        )
        
        with st.expander("View Mermaid code"):
            st.code(mmd, language="markdown")

    # Separate section for the rendered diagram
    st.divider()
    st.subheader("📊 Site Flow Diagram")
    
    render_mermaid(mmd)