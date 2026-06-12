import io
import os
import re
import sqlite3
import hashlib
import time
from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st
import altair as alt
import plotly.express as px
import plotly.graph_objects as go

try:
    import pdfplumber
except Exception:
    pdfplumber = None

APP_TITLE = "Young Academics Compliance Benchmarking Tool"
APP_VERSION = "v4.0 — Quarter chips + table exports"
DB_PATH = "compliance_history.sqlite3"
LOGO_URL = "https://www.youngacademics.com.au/application/themes/youngacademics/assets/images/logo.svg"
SIGNIFICANT_LAWS = {"165", "166", "167"}



def show_soft_loading(message="Please wait. Updating..."):
    """Show a non-blocking YA-styled status message before a Streamlit rerun/action.

    Important: this deliberately does NOT use a fixed full-screen overlay.
    A fixed overlay can remain visible while Streamlit is processing and make the
    app look frozen/hung during uploads.
    """
    st.markdown("""
    <style>
      .ya-success-panel {
        background: rgba(255,255,255,.92);
        border: 1px solid rgba(255,255,255,.72);
        box-shadow: 0 22px 60px rgba(0,0,0,.18);
        border-radius: 26px;
        padding: 24px 28px;
        margin: 18px 0 24px;
        color: #004f57;
      }
      .ya-success-title {
        font-size: 24px;
        font-weight: 950;
        margin-bottom: 16px;
      }
      .ya-success-grid {
        display: grid;
        grid-template-columns: repeat(4,minmax(0,1fr));
        gap: 12px;
      }
      .ya-success-grid div {
        background: #eaf6f8;
        border-radius: 18px;
        padding: 16px;
        font-weight: 800;
        color: #004f57;
      }
      .ya-duplicate-panel {
        background: rgba(255,248,216,.96);
        border: 2px solid #f1c232;
        box-shadow: 0 18px 48px rgba(0,0,0,.14);
        border-radius: 24px;
        padding: 20px 24px;
        margin: 18px 0;
        color: #3d3300;
      }
      .ya-duplicate-panel h3 {
        margin: 0 0 8px;
        font-size: 22px;
      }
      .ya-duplicate-list {
        margin: 10px 0 0 0;
        padding-left: 18px;
        font-weight: 800;
      }
    </style>
    """, unsafe_allow_html=True)

    safe_message = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    st.info(safe_message)
    time.sleep(0.05)


DEFAULT_PROVIDER_RULES = [
    ("Young Academics", ["young academics"]),
    ("Affinity", ["affinity education", "milestones", "papilio", "kids academy", "aussie kindies", "little beginnings"]),
    ("OSHClub & Helping Hands", ["oshclub", "helping hands", "os hclub"]),
    ("Little Zak's Academy", ["little zak", "little zaks"]),
    ("Jenny's Kindergarten", ["jenny's kindergarten", "jennys kindergarten"]),
    ("Oz Education", ["oz education"]),
    ("Only About Children", ["only about children"]),
    ("TheirCare", ["theircare"]),
    ("Guardian Childcare/Education", ["guardian childcare", "guardian child care", "guardian"]),
    ("Goodstart Early Learning", ["goodstart"]),
    ("Camp Australia", ["camp australia"]),
    ("Busy Bees", ["busy bees"]),
    ("Mini Masterminds", ["mini masterminds"]),
    ("TeamKids", ["teamkids"]),
    ("SCECS OSHC", ["scecs"]),
    ("Aspire OSHC", ["aspire oshc"]),
    ("Story House Early Learning", ["story house"]),
    ("MindChamps", ["mindchamps"]),
    ("Montessori Academy", ["montessori academy"]),
    ("Reggio Emilia Early Learning", ["reggio emilia"]),
    ("Learn & Laugh", ["learn & laugh"]),
]

LAW_RE = re.compile(r"\b(?:Law\s*)?(165|166|167|161A|162A|\d{2,3}[A-Z]?)\s*(?:\([^\)]*\))?", re.I)
REG_RE = re.compile(r"\bRegulation\s*(\d{2,3}[A-Z]*(?:AAC|AA|A|B|C|D)?)\s*(?:\([^\)]*\))?", re.I)
ID_RE = re.compile(r"\b((?:SE|PR)-\d{8})\b")
DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")

st.set_page_config(page_title=APP_TITLE, page_icon="🔒", layout="wide")

YA_CSS = """
<style>
:root{
  --ya-bg:#357b84;
  --ya-bg2:#2c6f77;
  --ya-navy:#08245c;
  --ya-teal:#357b84;
  --ya-teal-dark:#00504f;
  --ya-button:#8edfe4;
  --ya-button-hover:#a7eef2;
  --ya-soft:#eaf6f8;
  --ya-line:#b8dce1;
  --ya-yellow:#fff200;
  --ya-ink:#10242a;
}
html, body, [data-testid="stAppViewContainer"]{
  background:linear-gradient(180deg,var(--ya-bg) 0%, var(--ya-bg2) 100%) !important;
  color:#ffffff !important;
}
[data-testid="stHeader"]{background:transparent!important;}
.block-container{padding-top:1.25rem; padding-bottom:3rem; max-width:1280px;}

/* Main header */
.ya-shell{
  background:rgba(255,255,255,.96);
  border-radius:24px;
  padding:24px 28px;
  box-shadow:0 18px 42px rgba(0,0,0,.18);
  margin-bottom:22px;
  border:1px solid rgba(255,255,255,.72);
}
.ya-header{display:flex; align-items:center; justify-content:space-between; gap:18px;}
.ya-brand{display:flex; align-items:center; gap:22px;}
.ya-logo{width:200px; max-width:34vw; background:#fff; padding:6px; border-radius:14px;}
.ya-title h1{font-size:31px; line-height:1.06; color:#357b84!important; margin:0; font-weight:900; letter-spacing:-.02em; text-shadow:none!important;}
.ya-title p{margin:4px 0 0 0; color:var(--ya-teal-dark)!important; font-size:15px;}
.ya-version{background:var(--ya-navy); color:#fff; border-radius:999px; padding:9px 14px; font-weight:900; font-size:12px; white-space:nowrap; box-shadow:0 6px 14px rgba(8,36,92,.18);}
.ya-note{margin-top:16px; padding:14px 16px; border-left:5px solid var(--ya-teal); background:var(--ya-soft); border-radius:14px; color:var(--ya-teal-dark)!important; font-weight:650;}
.ya-disclaimer{margin-top:10px; font-size:12px; line-height:1.4; color:#35535a!important;}

/* Section cards */
.ya-section-card{
  background:rgba(255,255,255,.13);
  border:1px solid rgba(255,255,255,.25);
  border-radius:22px;
  padding:20px;
  margin:14px 0 22px;
  box-shadow:0 10px 28px rgba(0,0,0,.10);
}
.ya-panel-title{font-size:22px; font-weight:900; color:#fff; margin:0 0 12px;}
.ya-pill{display:inline-block; background:#ffffff; color:var(--ya-teal-dark); border:1px solid var(--ya-line); border-radius:999px; padding:7px 11px; font-weight:900; font-size:12px; margin:2px 6px 2px 0;}
.ya-warning{background:#fff8c9; border:2px solid var(--ya-yellow); color:#372f00; border-radius:16px; padding:12px 16px; margin:16px 0; box-shadow:0 6px 16px rgba(0,0,0,.12);}
.ya-warning *{color:#372f00!important;}

/* Headings and body text */
h1,h2,h3,h4,.stMarkdown h1,.stMarkdown h2,.stMarkdown h3{color:#ffffff!important; font-weight:900!important;}
.ya-shell h1,.ya-shell .ya-title h1{color:#357b84!important;}
.ya-shell p,.ya-shell strong{color:#00504f!important;}
p,li,.stMarkdown,.stCaption,[data-testid="stCaptionContainer"]{color:#eefbfc!important;}
label,[data-testid="stWidgetLabel"],[data-testid="stWidgetLabel"] p{color:#ffffff!important; font-weight:800!important;}

/* Inputs */
input, textarea, select{border-radius:12px!important; color:#10242a!important; background:#ffffff!important;}
[data-baseweb="input"], [data-baseweb="select"], [data-baseweb="textarea"]{border-radius:12px!important; background:#ffffff!important; color:#10242a!important;}
[data-baseweb="select"] *{color:#10242a!important;}
[data-baseweb="popover"] *{color:#10242a!important;}
[data-baseweb="menu"] *{color:#10242a!important; background:#ffffff!important;}
[data-baseweb="menu"] li, [role="option"], [role="option"] *{color:#10242a!important; background:#ffffff!important;}
[data-baseweb="menu"] li:hover, [role="option"]:hover{background:#eaf6f8!important;}
/* Disabled buttons remain readable */
.stButton>button:disabled,.stDownloadButton>button:disabled{background:#dceff2!important; color:#357b84!important; box-shadow:none!important; opacity:.95!important;}
[data-baseweb="tag"]{background:#357b84!important; color:#fff!important; border-radius:8px!important;}
[data-baseweb="tag"] span{color:#fff!important;}
.stSelectbox div, .stMultiSelect div, .stTextInput div{color:#10242a!important;}


/* File uploaders */
[data-testid="stFileUploader"] section{
  background:rgba(234,246,248,.16)!important;
  border:1.5px dashed rgba(255,255,255,.55)!important;
  border-radius:18px!important;
}
[data-testid="stFileUploaderDropzone"]{
  background:rgba(234,246,248,.16)!important;
  border:1.5px dashed rgba(255,255,255,.55)!important;
  border-radius:18px!important;
}
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzone"] p{color:#ffffff!important;}
[data-testid="stFileUploaderDropzone"] svg,
[data-testid="stFileUploaderDropzone"] path{color:var(--ya-button)!important; fill:var(--ya-button)!important;}
[data-testid="stFileUploader"] button{
  background:linear-gradient(180deg,var(--ya-button),#61c9d0)!important;
  color:#00393c!important;
  border:0!important;
  border-radius:12px!important;
  font-weight:900!important;
  box-shadow:0 5px 0 #1d6d75, 0 10px 18px rgba(0,0,0,.18)!important;
}
[data-testid="stFileUploader"] button:hover{background:linear-gradient(180deg,var(--ya-button-hover),#74d8df)!important; color:#002f32!important;}

/* Buttons */
.stButton>button,.stDownloadButton>button{
  background:linear-gradient(180deg,var(--ya-button),#61c9d0)!important;
  color:#00393c!important;
  border:0!important;
  border-radius:999px!important;
  padding:.72rem 1.15rem!important;
  font-weight:900!important;
  box-shadow:0 6px 0 #1d6d75, 0 13px 22px rgba(0,0,0,.22)!important;
  transition:transform .08s ease, box-shadow .08s ease, filter .12s ease!important;
}
.stButton>button:hover,.stDownloadButton>button:hover{filter:brightness(1.04)!important; transform:translateY(-1px)!important; box-shadow:0 7px 0 #1d6d75, 0 15px 26px rgba(0,0,0,.25)!important;}
.stButton>button:active,.stDownloadButton>button:active{transform:translateY(5px)!important; box-shadow:0 1px 0 #1d6d75, 0 8px 14px rgba(0,0,0,.22)!important;}

/* Expander / accordion */
[data-testid="stExpander"]{
  background:rgba(255,255,255,.10)!important;
  border:1px solid rgba(255,255,255,.24)!important;
  border-radius:18px!important;
  overflow:hidden;
}
[data-testid="stExpander"] summary p{color:#ffffff!important; font-weight:900!important;}

/* Executive KPI cards */
[data-testid="stMetric"]{
  background:#ffffff!important;
  border:1px solid var(--ya-line)!important;
  padding:18px 18px!important;
  border-radius:20px!important;
  box-shadow:0 10px 24px rgba(0,0,0,.16)!important;
  min-height:112px;
}
[data-testid="stMetric"] *{color:var(--ya-navy)!important;}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] *{color:var(--ya-teal)!important; font-weight:900!important;}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] *{color:var(--ya-navy)!important; font-weight:950!important;}

/* Tabs */
.stTabs [data-baseweb="tab-list"]{gap:10px; border-bottom:1px solid rgba(255,255,255,.18); padding-bottom:8px;}
.stTabs [data-baseweb="tab"]{
  border-radius:999px!important;
  padding:9px 18px!important;
  background:#eaf6f8!important;
  border:1px solid var(--ya-line)!important;
  color:var(--ya-teal-dark)!important;
  font-weight:900!important;
}
.stTabs [data-baseweb="tab"] p{color:var(--ya-teal-dark)!important; font-weight:900!important;}
.stTabs [aria-selected="true"]{background:var(--ya-navy)!important; border-color:var(--ya-navy)!important;}
.stTabs [aria-selected="true"] p{color:#ffffff!important;}

/* v3.8 clearer active navigation / expander states */
.stTabs [data-baseweb="tab"]{background:#eaf7f8!important;color:#00504f!important;box-shadow:0 2px 8px rgba(0,0,0,.08)!important;}
.stTabs [data-baseweb="tab"] p{color:#00504f!important;}
.stTabs [data-baseweb="tab"][aria-selected="true"]{background:#08245c!important;border:2px solid #8edfe4!important;box-shadow:0 6px 18px rgba(8,36,92,.32)!important;}
.stTabs [data-baseweb="tab"][aria-selected="true"] p{color:#ffffff!important;}
details[data-testid="stExpander"] summary{background:rgba(255,255,255,.14)!important;color:#ffffff!important;border-radius:14px!important;}
details[data-testid="stExpander"] summary *{color:#ffffff!important;font-weight:900!important;}
details[data-testid="stExpander"][open] summary{background:#08245c!important;color:#ffffff!important;}


/* Tables */
[data-testid="stDataFrame"]{background:#ffffff; border-radius:16px; overflow:hidden; box-shadow:0 10px 22px rgba(0,0,0,.14);}
[data-testid="stDataFrame"] *{color:#10242a!important;}

/* Notes cards */
.ya-note-grid{display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:14px; margin:12px 0 18px;}
.ya-note-card{background:#ffffff; border-radius:18px; padding:16px; min-height:145px; box-shadow:0 10px 22px rgba(0,0,0,.16); border:1px solid #b8dce1;}
.ya-note-card h4{margin:0 0 8px 0; color:#00504f!important; font-size:14px;}
.ya-note-card p{margin:0; color:#10242a!important; font-size:13px; line-height:1.35;}
@media(max-width:900px){.ya-note-grid{grid-template-columns:1fr 1fr}.ya-header{align-items:flex-start}.ya-brand{align-items:flex-start}.ya-logo{width:150px}.ya-title h1{font-size:24px}}


/* Multi-select cleanup: removes the odd white dot/pill artefact */
[data-baseweb="tag"]::before, [data-baseweb="tag"]::after{display:none!important; content:none!important;}
[data-baseweb="tag"]{padding-left:10px!important; margin-left:0!important;}
[data-baseweb="tag"] > div:first-child{display:none!important;}
[data-testid="stMultiSelect"] [data-baseweb="tag"]{background:#357b84!important; border:1px solid #8edfe4!important;}

/* Clean white content panels */
.ya-white-panel{background:#ffffff; border-radius:22px; padding:18px; box-shadow:0 10px 24px rgba(0,0,0,.14); border:1px solid #b8dce1; margin:12px 0 18px;}
.ya-white-panel h3,.ya-white-panel h4{color:#00504f!important; margin-top:0;}
.ya-white-panel p,.ya-white-panel li{color:#10242a!important;}

.ya-provider-title{background:#ffffff; border-radius:24px; padding:24px; box-shadow:0 12px 28px rgba(0,0,0,.16); border-left:8px solid #8edfe4; margin-bottom:18px;}
.ya-provider-title h1{color:#00504f!important; margin:0 0 6px 0;}
.ya-provider-title p{color:#10242a!important; margin:0;}

/* Modern glass dashboard */
.ya-dashboard-card{
  background:rgba(255,255,255,.18);
  border:1px solid rgba(255,255,255,.32);
  border-radius:26px;
  padding:18px 18px 10px;
  box-shadow:0 18px 38px rgba(0,0,0,.16);
  backdrop-filter:blur(14px);
  -webkit-backdrop-filter:blur(14px);
  margin:8px 0 18px;
}
.ya-dashboard-card h3{
  color:#ffffff!important;
  margin:0 0 6px 0!important;
  padding:0 4px 8px 4px!important;
  font-size:18px!important;
  letter-spacing:-.01em;
}
.ya-chart-caption{color:#d8f4f6!important; font-size:12px; margin-top:-4px; padding-left:4px;}



/* Upload review table - no dimming/backdrop during edits */
[data-baseweb="modal"]{background:transparent!important;}
[data-baseweb="modal"] > div{background:transparent!important;}
[data-baseweb="popover"]{z-index:999999!important; opacity:1!important;}
[data-baseweb="popover"] ul{max-height:320px!important; overflow:auto!important;}
[data-testid="stAppViewContainer"], .main, .block-container{opacity:1!important; filter:none!important;}

.ya-upload-review-card{
  background:#ffffff;
  border-radius:20px;
  overflow:hidden;
  box-shadow:0 14px 30px rgba(0,0,0,.16);
  border:1px solid #b8dce1;
  margin:14px 0 22px;
}
.ya-upload-row{
  border-bottom:1px solid #e2edf0;
  padding:8px 10px;
  color:#10242a!important;
}
.ya-upload-head{
  background:#f2f6f8;
  border-bottom:1px solid #d8e6ea;
  padding:10px;
  font-weight:900;
  color:#51636b!important;
}
.ya-upload-file{font-weight:750; color:#10242a!important; padding-top:8px; overflow-wrap:anywhere;}
.ya-upload-status{font-weight:750; color:#10242a!important; padding-top:8px; font-size:13px;}
.ya-upload-remove button{
  width:42px!important;
  height:40px!important;
  padding:0!important;
  border-radius:12px!important;
  background:#ffffff!important;
  color:#b42318!important;
  box-shadow:none!important;
  border:1.5px solid #f4b0aa!important;
  font-size:17px!important;
}
.ya-upload-remove button:hover{background:#fff1f0!important; transform:none!important; box-shadow:none!important;}
.ya-upload-review-card [data-testid="column"]{padding:0 4px!important;}




/* v2.8 compact upload review table */
.ya-review-shell{margin:16px 0 12px;}
.ya-review-intro{
  background:rgba(255,255,255,.14);
  border:1px solid rgba(255,255,255,.28);
  border-radius:22px;
  padding:16px 18px;
  box-shadow:0 12px 28px rgba(0,0,0,.12);
}
.ya-review-eyebrow{color:#ffffff!important;font-weight:950;font-size:22px;letter-spacing:-.02em;}
.ya-review-copy{color:#d9f4f6!important;font-size:13px;margin-top:3px;}
.ya-review-table{
  background:rgba(255,255,255,.96);
  border:1px solid rgba(255,255,255,.72);
  border-radius:22px;
  box-shadow:0 16px 34px rgba(0,0,0,.16);
  padding:10px 14px;
  margin:16px 0 18px;
}
.ya-review-header{
  background:#eef6f8;
  border-radius:16px;
  padding:10px 12px;
  margin-bottom:4px;
  color:#00504f!important;
  font-size:12px;
  font-weight:950;
  text-transform:uppercase;
  letter-spacing:.04em;
}
.ya-review-row{
  border-bottom:1px solid #dcebee;
  padding:8px 0 8px;
}
.ya-review-row.last{border-bottom:none;}
.ya-review-file{
  color:#10242a!important;
  font-size:13px;
  font-weight:850;
  line-height:1.2;
  overflow-wrap:anywhere;
  padding-top:10px;
}
.ya-review-existing,.ya-review-status-text{
  color:#10242a!important;
  font-size:13px;
  font-weight:800;
  padding-top:10px;
}
.ya-review-status-text.ready{color:#006b3d!important;}
.ya-review-status-text.check{color:#805300!important;}
.ya-review-status-text.duplicate{color:#a61616!important;}
.ya-review-table [data-testid="column"]{padding:0 .25rem!important;}
.ya-review-table [data-baseweb="select"]{
  min-height:40px!important;
  border:1px solid #c6dce0!important;
  border-radius:12px!important;
  background:#ffffff!important;
}
.ya-review-table [data-baseweb="select"] *{
  color:#10242a!important;
  font-size:13px!important;
  font-weight:650!important;
}
.ya-review-table .stButton>button{
  width:40px!important;height:40px!important;min-height:40px!important;padding:0!important;
  border-radius:12px!important;background:#fff4f3!important;color:#b42318!important;
  border:1px solid #ffb4ad!important;box-shadow:0 4px 10px rgba(180,35,24,.10)!important;
  font-size:16px!important;
}
.ya-review-table .stButton>button:hover{background:#ffe7e5!important;color:#7a130b!important;transform:none!important;}
.ya-removed-note{background:#eaf6f8;color:#00504f!important;border:1px solid #b8dce1;border-radius:16px;padding:12px 14px;font-weight:800;margin:12px 0 18px;}
/* Stop dropdown/popover from dimming or tinting the page */
[data-baseweb="modal"], [data-baseweb="modal"] > div, [data-baseweb="layer"], div[role="presentation"]{background:transparent!important;opacity:1!important;filter:none!important;}
[data-baseweb="popover"]{z-index:999999!important;opacity:1!important;filter:none!important;}
[data-baseweb="popover"] *, [data-baseweb="menu"] *, [role="listbox"] *{opacity:1!important;filter:none!important;}
[data-baseweb="popover"] ul, [data-baseweb="menu"], [role="listbox"]{background:#ffffff!important;color:#10242a!important;max-height:360px!important;overflow:auto!important;}
[data-baseweb="popover"] li, [role="option"]{color:#10242a!important;background:#ffffff!important;}
[data-baseweb="popover"] li:hover, [role="option"]:hover{background:#eaf6f8!important;color:#00504f!important;}
.stApp, [data-testid="stAppViewContainer"], .main, .block-container{opacity:1!important;filter:none!important;}
@media(max-width:1000px){.ya-review-file{font-size:12px}.ya-review-table{padding:8px}.ya-review-header{display:none}}


/* Keep app from visually dimming during upload-review interactions */
[data-testid="stStatusWidget"]{display:none!important;}
[data-testid="stDecoration"]{display:none!important;}

/* Hide Streamlit menu/footer */
#MainMenu, footer{visibility:hidden;}

/* v3.0 less-Streamlit polish */
#MainMenu, footer, header [data-testid="stToolbar"], [data-testid="stDeployButton"]{visibility:hidden!important; height:0!important;}
[data-testid="stStatusWidget"]{display:none!important;}
.ya-review-table-stable{padding:14px 16px!important; background:rgba(255,255,255,.98)!important;}
.ya-review-table-stable .ya-review-header{border-radius:14px;background:#eef7f8;color:#00504f!important;padding:10px 12px!important;white-space:nowrap;}
.ya-review-table-stable .ya-review-row{padding:9px 0!important;border-bottom:1px solid #d9eaed!important;}
.ya-review-table-stable .ya-review-file{display:flex;align-items:center;gap:10px;color:#10242a!important;font-size:13px!important;font-weight:850!important;padding-top:0!important;min-height:42px;}
.ya-file-icon{display:inline-flex;align-items:center;justify-content:center;min-width:42px;height:34px;border-radius:10px;background:#eaf6f8;color:#00504f!important;border:1px solid #b8dce1;font-size:11px;font-weight:950;letter-spacing:.04em;}
.ya-review-table-stable [data-baseweb="select"]{height:42px!important;min-height:42px!important;background:#f8fbfc!important;border:1px solid #c9dfe3!important;border-radius:12px!important;box-shadow:none!important;}
.ya-review-table-stable [data-baseweb="select"] > div{height:42px!important;min-height:42px!important;align-items:center!important;}
.ya-review-table-stable [data-baseweb="select"] *{color:#10242a!important;font-size:13px!important;font-weight:700!important;}
.ya-review-existing{min-height:42px;display:flex;align-items:center;color:#10242a!important;font-weight:850!important;padding-top:0!important;}
.ya-review-status-text{min-height:42px;display:flex;align-items:center;padding-top:0!important;font-size:12px!important;line-height:1.2!important;}
.ya-review-status-text.ready{color:#027a48!important;}
.ya-review-status-text.check{color:#936300!important;}
.ya-review-status-text.duplicate{color:#b42318!important;}
.ya-form-hint{color:#dff7f9!important;font-size:12px;font-weight:700;padding-top:12px;}
/* Make submit buttons read as app controls */
button[kind="primaryFormSubmit"], button[kind="secondaryFormSubmit"]{border-radius:999px!important;font-weight:900!important;}
button[kind="primaryFormSubmit"]{background:#8edfe4!important;color:#00393c!important;border:0!important;box-shadow:0 5px 0 #1d6d75,0 10px 18px rgba(0,0,0,.18)!important;}
button[kind="secondaryFormSubmit"]{background:#ffffff!important;color:#00504f!important;border:1px solid #b8dce1!important;box-shadow:0 6px 14px rgba(0,0,0,.12)!important;}
/* Stop BaseWeb dropdown overlay/backdrop from visually tinting the page */
[data-baseweb="layer"], [data-baseweb="layer"] > div{background:transparent!important;opacity:1!important;filter:none!important;}
[data-baseweb="popover"]{background:transparent!important;opacity:1!important;filter:none!important;z-index:2147483647!important;}
[data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"]{background:#ffffff!important;border:1px solid #c9dfe3!important;box-shadow:0 18px 34px rgba(0,0,0,.20)!important;border-radius:14px!important;overflow:auto!important;max-height:340px!important;}
[data-baseweb="popover"] [role="option"], [data-baseweb="menu"] li{background:#ffffff!important;color:#10242a!important;}
[data-baseweb="popover"] [role="option"]:hover, [data-baseweb="menu"] li:hover{background:#eaf6f8!important;color:#00504f!important;}



/* v3.0 upload review readability override */
.ya-review-table-stable{
  background:#ffffff!important;
  border-radius:18px!important;
  padding:18px!important;
  box-shadow:0 14px 34px rgba(0,0,0,.18)!important;
  border:1px solid #b8dce1!important;
}
.ya-review-table-stable .ya-review-header{
  background:#eef7f8!important;
  color:#004f55!important;
  font-size:13px!important;
  padding:12px 14px!important;
  border-radius:12px!important;
  letter-spacing:.03em!important;
}
.ya-review-table-stable .ya-review-row{
  background:#ffffff!important;
  padding:12px 0!important;
  border-bottom:1px solid #d6e7eb!important;
}
.ya-review-table-stable .ya-review-file{
  color:#0f2430!important;
  font-size:14px!important;
  font-weight:800!important;
  line-height:1.25!important;
  word-break:break-word!important;
}
.ya-file-icon{
  background:#e5f5f7!important;
  color:#005f66!important;
  border:1px solid #add8dd!important;
  min-width:44px!important;
  height:36px!important;
}
.ya-review-table-stable [data-baseweb="select"]{
  background:#ffffff!important;
  border:1.5px solid #bfd7dd!important;
  border-radius:12px!important;
  min-height:44px!important;
}
.ya-review-table-stable [data-baseweb="select"] *{
  color:#10242a!important;
  font-size:14px!important;
  font-weight:650!important;
}
.ya-review-existing{
  color:#10242a!important;
  font-size:14px!important;
  font-weight:800!important;
}
.ya-review-status-text{
  font-size:13px!important;
  font-weight:850!important;
  line-height:1.2!important;
  word-break:normal!important;
}
.ya-review-status-text.ready{color:#00834d!important;}
.ya-review-status-text.check{color:#b36b00!important;}
.ya-review-status-text.duplicate{color:#b42318!important;}
.ya-review-table-stable [data-testid="column"]{padding:0 .38rem!important;}
/* keep dropdown menus readable */
[data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"]{
  background:#ffffff!important;
  color:#10242a!important;
  border:1px solid #b8dce1!important;
  border-radius:14px!important;
  box-shadow:0 18px 40px rgba(0,0,0,.24)!important;
  max-height:420px!important;
}
[data-baseweb="popover"] [role="option"], [data-baseweb="menu"] li{
  color:#10242a!important;
  background:#ffffff!important;
  font-size:14px!important;
}
[data-baseweb="popover"] [role="option"]:hover, [data-baseweb="menu"] li:hover{
  background:#eaf6f8!important;
  color:#00504f!important;
}
</style>
"""
st.markdown(YA_CSS, unsafe_allow_html=True)



def hash_password(password: str, salt: str = None) -> Tuple[str, str]:
    if salt is None:
        salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return digest.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    check, _ = hash_password(password, salt)
    return check == stored_hash


def ensure_default_users():
    """Creates the initial admin users if they do not already exist."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    default_password = "YA2026!#123"
    for email in ["james.mh@youngacademics.com.au", "eric@youngacademics.com.au"]:
        exists = cur.execute("SELECT email FROM users WHERE email=?", (email,)).fetchone()
        if not exists:
            pw_hash, salt = hash_password(default_password)
            cur.execute(
                "INSERT INTO users(email, password_hash, salt, role, active, created_at, updated_at, created_by) VALUES (?,?,?,?,?,?,?,?)",
                (email, pw_hash, salt, "admin", 1, now, now, "system"),
            )
    con.commit(); con.close()


def current_user_email() -> str:
    return st.session_state.get("current_user", {}).get("email", "")


def current_user_role() -> str:
    return st.session_state.get("current_user", {}).get("role", "")


def is_admin() -> bool:
    return current_user_role() == "admin"


def log_audit(action: str, detail: str = ""):
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT INTO audit_logs(timestamp, user_email, role, action, detail) VALUES (?,?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), current_user_email() or "system", current_user_role() or "system", action, detail),
        )
        con.commit(); con.close()
    except Exception:
        pass


def authenticate_user(email: str, password: str):
    email = (email or "").strip().lower()
    if not email.endswith("@youngacademics.com.au"):
        return None, "Only @youngacademics.com.au emails are permitted."
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT email, password_hash, salt, role, active FROM users WHERE lower(email)=?", (email,)).fetchone()
    con.close()
    if not row:
        return None, "User not found. Ask an admin to create your account."
    if int(row[4]) != 1:
        return None, "This user is inactive. Ask an admin to reactivate the account."
    if not verify_password(password, row[1], row[2]):
        return None, "Invalid password."
    return {"email": row[0], "role": row[3]}, None


def render_login_screen():
    st.markdown(f"""
    <div class='ya-shell' style='max-width:820px;margin:7vh auto 24px;'>
      <div class='ya-header'>
        <div class='ya-brand'>
          <img class='ya-logo' src='{LOGO_URL}' />
          <div class='ya-title'>
            <h1>Compliance Benchmarking System</h1>
            <p>Secure internal access for Young Academics users</p>
          </div>
        </div>
        <div class='ya-version'>Role Login</div>
      </div>
      <div class='ya-note'>Admins can upload, delete and manage users. Standard users can view and export data only.</div>
      <div class='ya-disclaimer'>This system and its outputs are the property of Young Academics Early Learning Centre. Any unauthorised access, use, copying, distribution, or disclosure is strictly prohibited.</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        with st.form("simple_login_form"):
            email = st.text_input("Email", placeholder="name@youngacademics.com.au")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
        if submitted:
            user, err = authenticate_user(email, password)
            if err:
                st.error(err)
            else:
                st.session_state["current_user"] = user
                log_audit("login", "Successful login")
                st.rerun()


def require_login():
    init_db(create_defaults=True)
    if st.session_state.get("current_user"):
        return
    render_login_screen()
    st.stop()


def logout_button():
    c1, c2, c3 = st.columns([5, 2, 1])
    with c2:
        st.caption(f"Signed in: {current_user_email()} · {current_user_role().upper()}")
    with c3:
        if st.button("Logout", key="logout_btn"):
            log_audit("logout", "User logged out")
            st.session_state.pop("current_user", None)
            st.rerun()


def render_admin_user_manager_panel():
    if not is_admin():
        st.info("Admin user management is available to admins only.")
        return
    st.markdown("### Admin users")
    st.caption("Only admins can create users/admins, change passwords, deactivate accounts, and view audit logs.")
    con = sqlite3.connect(DB_PATH)
    users_df = pd.read_sql_query("SELECT email, role, active, created_at, updated_at, created_by FROM users ORDER BY role, email", con)
    logs_df = pd.read_sql_query("SELECT timestamp, user_email, role, action, detail FROM audit_logs ORDER BY timestamp DESC LIMIT 250", con)
    con.close()

    st.markdown("#### Current users")
    st.dataframe(users_df, use_container_width=True, hide_index=True, key="admin_users_table")

    c_create, c_edit = st.columns(2)
    with c_create:
        st.markdown("#### Create user / admin")
        with st.form("create_user_form"):
            new_email = st.text_input("New user email", placeholder="name@youngacademics.com.au")
            new_role = st.selectbox("Role", ["user", "admin"], key="new_user_role")
            new_pw = st.text_input("Set password", type="password", key="new_user_password")
            create_user = st.form_submit_button("Create account")
        if create_user:
            email = (new_email or "").strip().lower()
            if not email.endswith("@youngacademics.com.au"):
                st.error("User must have a @youngacademics.com.au email.")
            elif not new_pw:
                st.error("Enter a password.")
            else:
                try:
                    pw_hash, salt = hash_password(new_pw)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    con = sqlite3.connect(DB_PATH)
                    con.execute(
                        "INSERT INTO users(email, password_hash, salt, role, active, created_at, updated_at, created_by) VALUES (?,?,?,?,?,?,?,?)",
                        (email, pw_hash, salt, new_role, 1, now, now, current_user_email()),
                    )
                    con.commit(); con.close()
                    log_audit("create_user", f"Created {new_role}: {email}")
                    st.success(f"Created {new_role}: {email}")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That user already exists.")

    with c_edit:
        st.markdown("#### Change password / role / status")
        user_options = users_df["email"].tolist() if not users_df.empty else []
        if user_options:
            target = st.selectbox("Select user", user_options, key="admin_target_user")
            target_row = users_df[users_df["email"].eq(target)].iloc[0] if target else None
            role_index = ["user", "admin"].index(str(target_row["role"])) if target_row is not None and str(target_row["role"]) in ["user","admin"] else 0
            status_index = 0 if target_row is not None and int(target_row["active"]) == 1 else 1
            with st.form("edit_user_form"):
                new_role2 = st.selectbox("Role", ["user", "admin"], index=role_index, key="edit_user_role")
                active2 = st.selectbox("Status", ["Active", "Inactive"], index=status_index, key="edit_user_status")
                new_pw2 = st.text_input("New password (leave blank to keep current)", type="password", key="edit_user_password")
                update_user = st.form_submit_button("Update selected user")
            if update_user:
                if target == current_user_email() and active2 == "Inactive":
                    st.error("You cannot deactivate your own account while signed in.")
                else:
                    con = sqlite3.connect(DB_PATH)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    con.execute("UPDATE users SET role=?, active=?, updated_at=? WHERE email=?", (new_role2, 1 if active2 == "Active" else 0, now, target))
                    if new_pw2:
                        pw_hash, salt = hash_password(new_pw2)
                        con.execute("UPDATE users SET password_hash=?, salt=?, updated_at=? WHERE email=?", (pw_hash, salt, now, target))
                    con.commit(); con.close()
                    log_audit("update_user", f"Updated {target}: role={new_role2}, status={active2}, password_changed={bool(new_pw2)}")
                    st.success("User updated.")
                    st.rerun()

    with st.expander("Recent audit logs", expanded=False):
        st.dataframe(logs_df, use_container_width=True, hide_index=True, key="admin_audit_logs_table")


def init_db(create_defaults: bool = False):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            run_id TEXT, quarter TEXT, report_type TEXT, action_id TEXT,
            entity_id TEXT, provider TEXT, service_name TEXT, date_issued TEXT,
            action_type TEXT, raw_text TEXT, processed_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS breaches (
            run_id TEXT, quarter TEXT, action_id TEXT, provider TEXT,
            breach_code TEXT, breach_family TEXT, classification TEXT, processed_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, quarter TEXT, processed_at TEXT,
            actions_count INTEGER, breaches_count INTEGER, notes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            run_id TEXT, quarter TEXT, report_type TEXT, file_name TEXT,
            file_signature TEXT, actions_count INTEGER, breaches_count INTEGER,
            processed_at TEXT, PRIMARY KEY (quarter, report_type)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS service_master (
            service_approval_number TEXT PRIMARY KEY,
            provider_approval_number TEXT,
            service_name TEXT,
            provider_legal_name TEXT,
            parent_company TEXT,
            sub_brand TEXT,
            service_type TEXT,
            address TEXT,
            suburb TEXT,
            state TEXT,
            postcode TEXT,
            latitude REAL,
            longitude REAL,
            approved_places INTEGER,
            ldc TEXT,
            source_file TEXT,
            uploaded_by TEXT,
            uploaded_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','user')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT,
            updated_at TEXT,
            created_by TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user_email TEXT,
            role TEXT,
            action TEXT,
            detail TEXT
        )
    """)
    # Backward-compatible column adds.
    for table in ["actions", "breaches"]:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN processed_at TEXT")
        except sqlite3.OperationalError:
            pass
    for col in ["provider_legal_name", "parent_company", "sub_brand", "provider_approval_number", "service_approval_number"]:
        for table in ["actions", "breaches"]:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
    for table in ["actions", "reports", "runs"]:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN uploaded_by TEXT")
        except sqlite3.OperationalError:
            pass
    con.commit(); con.close()
    if create_defaults:
        ensure_default_users()


def _sqlite_table_columns(con, table_name: str) -> List[str]:
    """Return current SQLite table columns."""
    return [row[1] for row in con.execute(f"PRAGMA table_info({table_name})").fetchall()]


def _sqlite_safe_value(value):
    """Convert pandas/numpy values into SQLite-safe values."""
    if pd.isna(value):
        return None
    if isinstance(value, (dict, list, tuple, set)):
        return str(value)
    return value


def _ensure_sqlite_columns(con, table_name: str, df: pd.DataFrame):
    """Add any new dataframe columns to SQLite before saving.

    This prevents pandas.to_sql DatabaseError when the parser adds a new field
    such as reason_text, provider_legal_name, parent_company, sub_brand, etc.
    """
    if df is None or df.empty:
        return
    existing = set(_sqlite_table_columns(con, table_name))
    for col in df.columns:
        if col not in existing:
            safe_col = str(col).replace('"', '""')
            con.execute(f'ALTER TABLE {table_name} ADD COLUMN "{safe_col}" TEXT')
            existing.add(col)


def _append_dataframe(con, table_name: str, df: pd.DataFrame):
    """Append dataframe after aligning columns with the live SQLite schema."""
    if df is None or df.empty:
        return
    frame = df.copy()
    _ensure_sqlite_columns(con, table_name, frame)
    table_cols = _sqlite_table_columns(con, table_name)
    for col in table_cols:
        if col not in frame.columns:
            frame[col] = None
    frame = frame[table_cols]
    frame = frame.applymap(_sqlite_safe_value)
    frame.to_sql(table_name, con, if_exists="append", index=False)


def _upsert_reports(con, report_meta: pd.DataFrame):
    """Save report metadata using INSERT OR REPLACE to avoid duplicate PK crashes."""
    if report_meta is None or report_meta.empty:
        return
    frame = report_meta.copy()
    _ensure_sqlite_columns(con, "reports", frame)
    table_cols = _sqlite_table_columns(con, "reports")
    for col in table_cols:
        if col not in frame.columns:
            frame[col] = None
    frame = frame[table_cols].applymap(_sqlite_safe_value)

    quoted_cols = ",".join([f'"{c}"' for c in table_cols])
    placeholders = ",".join(["?"] * len(table_cols))
    sql = f'INSERT OR REPLACE INTO reports ({quoted_cols}) VALUES ({placeholders})'
    con.executemany(sql, frame.itertuples(index=False, name=None))


def save_to_db(actions: pd.DataFrame, breaches: pd.DataFrame, report_meta: pd.DataFrame = None, uploaded_by: str = ""):
    """Save extracted upload data safely.

    Fixes upload failures caused by dataframe columns not matching the SQLite
    table schema, especially fields added by the newer PDF parser.
    """
    init_db()
    con = sqlite3.connect(DB_PATH)
    try:
        processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uploader = uploaded_by or current_user_email()

        actions_to_save = actions.copy() if actions is not None else pd.DataFrame()
        breaches_to_save = breaches.copy() if breaches is not None else pd.DataFrame()

        if not actions_to_save.empty:
            if "processed_at" not in actions_to_save.columns:
                actions_to_save["processed_at"] = processed_at
            if "uploaded_by" not in actions_to_save.columns:
                actions_to_save["uploaded_by"] = uploader
            _append_dataframe(con, "actions", actions_to_save)

        if not breaches_to_save.empty:
            if "processed_at" not in breaches_to_save.columns:
                breaches_to_save["processed_at"] = processed_at
            if "uploaded_by" not in breaches_to_save.columns:
                breaches_to_save["uploaded_by"] = uploader
            _append_dataframe(con, "breaches", breaches_to_save)

        if not actions_to_save.empty:
            run_id = str(actions_to_save["run_id"].iloc[0])
            quarters = sorted([str(q) for q in actions_to_save["quarter"].dropna().unique().tolist()])
            quarter = quarters[0] if len(quarters) == 1 else f"Bulk upload — {len(quarters)} quarters"
            con.execute(
                "INSERT OR REPLACE INTO runs(run_id, quarter, processed_at, actions_count, breaches_count, notes, uploaded_by) VALUES (?,?,?,?,?,?,?)",
                (run_id, quarter, processed_at, len(actions_to_save), len(breaches_to_save), "", uploader),
            )

        if report_meta is not None and not report_meta.empty:
            meta_to_save = report_meta.copy()
            if "processed_at" not in meta_to_save.columns:
                meta_to_save["processed_at"] = processed_at
            if "uploaded_by" not in meta_to_save.columns:
                meta_to_save["uploaded_by"] = uploader
            _upsert_reports(con, meta_to_save)

        con.commit()
    finally:
        con.close()


def load_history() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    init_db()
    con = sqlite3.connect(DB_PATH)
    actions = pd.read_sql_query("SELECT * FROM actions", con)
    breaches = pd.read_sql_query("SELECT * FROM breaches", con)
    runs = pd.read_sql_query("SELECT * FROM runs ORDER BY processed_at DESC", con)
    con.close()
    return actions, breaches, runs


def delete_run(run_id: str):
    log_audit("delete_run", f"Deleted run_id={run_id}")
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM actions WHERE run_id=?", (run_id,))
    con.execute("DELETE FROM breaches WHERE run_id=?", (run_id,))
    con.execute("DELETE FROM reports WHERE run_id=?", (run_id,))
    con.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
    con.commit(); con.close()


def load_reports_history() -> pd.DataFrame:
    init_db()
    con = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM reports ORDER BY processed_at DESC", con)
    finally:
        con.close()
    return df


SERVICE_MASTER_REQUIRED = {
    "ServiceApprovalNumber": ["serviceapprovalnumber", "service approval number", "service_approval_number", "service id"],
    "Provider Approval Number": ["provider approval number", "providerapprovalnumber", "provider_approval_number", "provider id"],
    "ServiceName": ["servicename", "service name"],
    "ProviderLegalName": ["providerlegalname", "provider legal name", "provider name"],
}


def _col_lookup(df: pd.DataFrame) -> Dict[str, str]:
    return {re.sub(r"[^a-z0-9]", "", str(c).lower()): c for c in df.columns}


def _find_col(df: pd.DataFrame, aliases: List[str]) -> str:
    lookup = _col_lookup(df)
    for a in aliases:
        key = re.sub(r"[^a-z0-9]", "", a.lower())
        if key in lookup:
            return lookup[key]
    return ""


def tidy_title(value: str) -> str:
    txt = re.sub(r"\s+", " ", str(value or "")).strip()
    if not txt:
        return ""
    if txt.isupper() or txt.islower():
        txt = txt.title()
    txt = txt.replace("Pty Ltd", "Pty Ltd").replace("Pty. Ltd.", "Pty Ltd").replace("Oshc", "OSHC").replace("Oosh", "OOSH")
    return txt


def infer_parent_subbrand(service_name: str, provider_legal_name: str, provider_approval_number: str = "") -> Tuple[str, str]:
    svc = re.sub(r"\s+", " ", str(service_name or "")).strip()
    legal = re.sub(r"\s+", " ", str(provider_legal_name or "")).strip()
    low_svc = svc.lower()
    low_legal = legal.lower()
    pr = str(provider_approval_number or "").strip()

    # Parent owner first. Do not group Little Zak's under Affinity.
    if "young academics" in low_svc or "young academics" in low_legal:
        parent = "Young Academics"
    elif "g8 education" in low_legal or pr == "PR-00000898":
        parent = "G8 Education"
    elif "affinity education" in low_legal or pr == "PR-40001112":
        parent = "Affinity"
    elif "goodstart" in low_svc or "goodstart" in low_legal:
        parent = "Goodstart Early Learning"
    elif "guardian" in low_svc or "guardian" in low_legal:
        parent = "Guardian Childcare/Education"
    elif "little zak" in low_svc or "little zaks" in low_svc or "m & w zaki" in low_legal or re.search(r"\blz\b", low_legal):
        parent = "Little Zak's Academy"
    elif "oshclub" in low_svc or "helping hands" in low_svc:
        parent = "OSHClub & Helping Hands"
    elif "theircare" in low_svc or "theircare" in low_legal:
        parent = "TheirCare"
    elif "camp australia" in low_svc or "camp australia" in low_legal:
        parent = "Camp Australia"
    elif "busy bees" in low_svc or "busy bees" in low_legal:
        parent = "Busy Bees"
    elif "only about children" in low_svc or "only about children" in low_legal:
        parent = "Only About Children"
    elif "mini masterminds" in low_svc or "mini masterminds" in low_legal:
        parent = "Mini Masterminds"
    elif "teamkids" in low_svc or "teamkids" in low_legal:
        parent = "TeamKids"
    elif "oz education" in low_svc or "oz education" in low_legal:
        parent = "Oz Education"
    else:
        parent = tidy_title(legal) or normalise_provider_stem(svc)

    brand_patterns = [
        ("Little Zak", "Little Zak's Academy"),
        ("Milestones", "Milestones Early Learning"),
        ("Papilio", "Papilio Early Learning"),
        ("Kids Academy", "Kids Academy"),
        ("Aussie Kindies", "Aussie Kindies"),
        ("Little Beginnings", "Little Beginnings"),
        ("Community Kids", "Community Kids"),
        ("World of Learning", "World of Learning"),
        ("Great Beginnings", "Great Beginnings"),
        ("Greenwood", "Greenwood"),
        ("Bambino", "Bambino's Kindergarten"),
        ("Creative Garden", "Creative Garden"),
        ("Kinder Haven", "Kinder Haven"),
        ("Kindy Patch", "Kindy Patch"),
        ("NurtureOne", "NurtureOne"),
        ("Penguin", "Penguin Childcare"),
        ("Pelicans", "Pelicans Childcare"),
        ("Learning Sanctuary", "The Learning Sanctuary"),
        ("Guardian", "Guardian"),
        ("Goodstart", "Goodstart Early Learning"),
        ("OSHClub", "OSHClub"),
        ("Helping Hands", "Helping Hands"),
        ("TheirCare", "TheirCare"),
        ("Camp Australia", "Camp Australia"),
        ("Young Academics", "Young Academics"),
    ]
    sub_brand = ""
    for pat, label in brand_patterns:
        if pat.lower() in low_svc:
            sub_brand = label
            break
    if not sub_brand:
        sub_brand = parent
    return parent, sub_brand


def normalise_service_master_csv(file_obj) -> pd.DataFrame:
    raw = pd.read_csv(file_obj)
    cols = {target: _find_col(raw, aliases) for target, aliases in SERVICE_MASTER_REQUIRED.items()}
    missing = [k for k, v in cols.items() if not v]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    out = pd.DataFrame()
    out["service_approval_number"] = raw[cols["ServiceApprovalNumber"]].astype(str).str.strip()
    out["provider_approval_number"] = raw[cols["Provider Approval Number"]].astype(str).str.strip()
    out["service_name"] = raw[cols["ServiceName"]].astype(str).str.strip()
    out["provider_legal_name"] = raw[cols["ProviderLegalName"]].astype(str).str.strip()
    optional_map = {
        "service_type": ["servicetype", "service type"],
        "address": ["address", "serviceaddress", "service address"],
        "suburb": ["suburb"],
        "state": ["state"],
        "postcode": ["postcode", "post code"],
        "latitude": ["latitude", "lat"],
        "longitude": ["longitude", "lon", "lng"],
        "approved_places": ["numberofapprovedplaces", "number of approved places", "approved places"],
        "ldc": ["ldc"],
    }
    for new_col, aliases in optional_map.items():
        c = _find_col(raw, aliases)
        out[new_col] = raw[c] if c else ""
    parents, brands = [], []
    for _, r in out.iterrows():
        parent, brand = infer_parent_subbrand(r.get("service_name", ""), r.get("provider_legal_name", ""), r.get("provider_approval_number", ""))
        parents.append(parent); brands.append(brand)
    out["parent_company"] = parents
    out["sub_brand"] = brands
    out = out[out["service_approval_number"].str.match(r"^SE-\d{8}$", na=False)].copy()
    out = out.drop_duplicates(subset=["service_approval_number"], keep="last")
    return out


def save_service_master(master_df: pd.DataFrame, source_file: str = ""):
    init_db()
    df = master_df.copy()
    df["source_file"] = source_file
    df["uploaded_by"] = current_user_email()
    df["uploaded_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM service_master")
    df.to_sql("service_master", con, if_exists="append", index=False)
    con.commit(); con.close()
    log_audit("upload_service_master", f"Uploaded service master: {source_file}; rows={len(df)}")


def load_service_master() -> pd.DataFrame:
    init_db()
    con = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM service_master", con)
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()
    return df


def enrich_with_service_master(actions: pd.DataFrame, breaches: pd.DataFrame, master_df: pd.DataFrame = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    a = actions.copy() if actions is not None else pd.DataFrame()
    b = breaches.copy() if breaches is not None else pd.DataFrame()
    if master_df is None:
        master_df = load_service_master()
    if master_df is None or master_df.empty or a.empty:
        return a, b
    sm = master_df.copy()
    svc_map = sm.drop_duplicates("service_approval_number").set_index("service_approval_number").to_dict("index") if "service_approval_number" in sm.columns else {}
    pr_map = sm.drop_duplicates("provider_approval_number").set_index("provider_approval_number").to_dict("index") if "provider_approval_number" in sm.columns else {}

    def enrich_row(row):
        ent = str(row.get("entity_id", "")).strip()
        rec = svc_map.get(ent) or pr_map.get(ent)
        out = row.copy()
        if rec:
            out["service_approval_number"] = rec.get("service_approval_number", "")
            out["provider_approval_number"] = rec.get("provider_approval_number", "")
            out["provider_legal_name"] = rec.get("provider_legal_name", "")
            out["parent_company"] = rec.get("parent_company", "")
            out["sub_brand"] = rec.get("sub_brand", "")
            # Main provider column becomes the business roll-up, not raw PDF text.
            out["provider"] = rec.get("parent_company", "") or rec.get("provider_legal_name", "") or out.get("provider", "")
            if not str(out.get("service_name", "")).strip() or looks_like_action_text(str(out.get("service_name", ""))):
                out["service_name"] = rec.get("service_name", out.get("service_name", ""))
        else:
            parent, brand = infer_parent_subbrand(row.get("service_name", ""), row.get("provider", ""), "")
            out["provider_legal_name"] = out.get("provider_legal_name", "") or ""
            out["parent_company"] = out.get("parent_company", "") or parent
            out["sub_brand"] = out.get("sub_brand", "") or brand
            if looks_like_action_text(str(out.get("provider", ""))):
                out["provider"] = parent
        return out

    if not a.empty:
        a = pd.DataFrame([enrich_row(r) for _, r in a.iterrows()])
    if not b.empty and not a.empty and "action_id" in a.columns:
        cols = [c for c in ["provider", "provider_legal_name", "parent_company", "sub_brand", "provider_approval_number", "service_approval_number"] if c in a.columns]
        mp = a.drop_duplicates("action_id").set_index("action_id")[cols].to_dict("index")
        for c in cols:
            b[c] = b.apply(lambda r, c=c: mp.get(r.get("action_id"), {}).get(c, r.get(c, "")), axis=1)
    return a, b


def read_pdf_text(uploaded_file) -> str:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is not installed. Run: pip install -r requirements.txt")
    data = uploaded_file.read()
    uploaded_file.seek(0)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = []
        for page in pdf.pages:
            pages.append(page.extract_text(x_tolerance=2, y_tolerance=4) or "")
    return "\n".join(pages)


MONTH_ABBR = {
    "january": "Jan", "february": "Feb", "march": "Mar", "april": "Apr", "may": "May", "june": "Jun",
    "july": "Jul", "august": "Aug", "september": "Sep", "october": "Oct", "november": "Nov", "december": "Dec",
}

REPORT_TYPE_OPTIONS = [
    "— Select report type —",
    "Service Enforcement",
    "Provider Approval Cancellation",
    "Service Approval Cancellation",
    "Involuntary Suspension",
    "Provider Enforcement",
]

def quarter_label(qnum: int, fy_start_yyyy: int) -> str:
    fy1 = str(fy_start_yyyy)[-2:]
    fy2 = str(fy_start_yyyy + 1)[-2:]
    if qnum == 1:
        return f"Q1 FY{fy1}/{fy2} — Jul–Sep {fy_start_yyyy}"
    if qnum == 2:
        return f"Q2 FY{fy1}/{fy2} — Oct–Dec {fy_start_yyyy}"
    if qnum == 3:
        return f"Q3 FY{fy1}/{fy2} — Jan–Mar {fy_start_yyyy + 1}"
    return f"Q4 FY{fy1}/{fy2} — Apr–Jun {fy_start_yyyy + 1}"

def quarter_options() -> List[str]:
    # Covers historic imports and the next few years. Enforced dropdown means labels stay consistent.
    years = range(2023, 2030)
    return ["— Select quarter —"] + [quarter_label(q, y) for y in years for q in (1, 2, 3, 4)]

def quarter_from_filename_or_text(source: str) -> str:
    # Handles filenames like Q1_Service_Enforcement_Action_Information_2025_2026.pdf
    m = re.search(r"Q([1-4]).*?(20\d{2})[_\-/](20\d{2})", source, re.I)
    if m:
        return quarter_label(int(m.group(1)), int(m.group(2)))
    return ""

def normalise_quarter_label(text: str, fallback: str = "") -> str:
    """Return a strict label like Q2 FY25/26 — Oct–Dec 2025 from NSW PDF header text or filename."""
    source = f"{fallback}\n{text or ''}"

    # 1) Best case: official header contains Qx FYyy/yy and month range.
    q = re.search(r"\bQ([1-4])\s*FY\s*(20)?(\d{2})\s*/\s*(20)?(\d{2})\b", source, re.I)
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+to\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})", source, re.I)
    if q and m:
        qnum = q.group(1)
        fy1 = q.group(3)
        fy2 = q.group(5)
        start = MONTH_ABBR[m.group(1).lower()]
        end = MONTH_ABBR[m.group(2).lower()]
        year = m.group(3)
        return f"Q{qnum} FY{fy1}/{fy2} — {start}–{end} {year}"

    # 2) Filename fallback: Q1_..._2025_2026.pdf → Q1 FY25/26 — Jul–Sep 2025.
    derived = quarter_from_filename_or_text(source)
    if derived:
        return derived

    # 3) Preserve already-standard labels only.
    clean = (fallback or "").strip()
    if re.match(r"^Q[1-4]\s+FY\d{2}/\d{2}\s+—\s+[A-Z][a-z]{2}–[A-Z][a-z]{2}\s+20\d{2}$", clean):
        return clean
    return "UNIDENTIFIED QUARTER — CHECK PDF"


def file_signature(uploaded_file) -> str:
    data = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    return hashlib.sha256(data).hexdigest()


def report_already_uploaded(quarter: str, report_type: str) -> int:
    con = sqlite3.connect(DB_PATH)
    try:
        count = con.execute("SELECT COUNT(*) FROM actions WHERE quarter=? AND report_type=?", (quarter, report_type)).fetchone()[0]
    finally:
        con.close()
    return int(count or 0)


def detect_report_type(text: str, file_name: str = "") -> str:
    """Classify NSW PDF report type from header/title text."""
    source = f"{file_name}\n{text[:4000]}".lower()
    if "provider approval cancellations" in source or "provider cancellations" in source:
        return "Provider Approval Cancellation"
    if "service approval cancellations" in source or "service cancellations" in source:
        return "Service Approval Cancellation"
    if "involuntary suspensions" in source or "grounds for involuntary suspension" in source:
        return "Involuntary Suspension"
    if "enforceable undertakings" in source or "emergency action notices" in source or "compliance notices" in source or "reason for enforcement action" in source:
        return "Service Enforcement"
    return "UNIDENTIFIED REPORT TYPE"


def delete_report_data(quarter: str, report_type: str):
    """Remove one quarter/report-type safely before replacing it."""
    log_audit("delete_report_data", f"Deleted/replaced {quarter} · {report_type}")
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    action_ids = [r[0] for r in cur.execute("SELECT action_id FROM actions WHERE quarter=? AND report_type=?", (quarter, report_type)).fetchall()]
    if action_ids:
        placeholders = ",".join(["?"] * len(action_ids))
        cur.execute(f"DELETE FROM breaches WHERE action_id IN ({placeholders})", action_ids)
    cur.execute("DELETE FROM actions WHERE quarter=? AND report_type=?", (quarter, report_type))
    cur.execute("DELETE FROM reports WHERE quarter=? AND report_type=?", (quarter, report_type))
    con.commit(); con.close()


def delete_report_files(report_rows: pd.DataFrame):
    """Admin-only bulk delete by individual report rows. Keeps users intact."""
    if report_rows is None or report_rows.empty:
        return 0
    init_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    deleted = 0
    for _, row in report_rows.iterrows():
        quarter = str(row.get("quarter", ""))
        report_type = str(row.get("report_type", ""))
        file_name = str(row.get("file_name", ""))
        run_id = str(row.get("run_id", ""))
        action_ids = [r[0] for r in cur.execute(
            "SELECT action_id FROM actions WHERE quarter=? AND report_type=? AND run_id=?",
            (quarter, report_type, run_id)
        ).fetchall()]
        if action_ids:
            placeholders = ",".join(["?"] * len(action_ids))
            cur.execute(f"DELETE FROM breaches WHERE action_id IN ({placeholders})", action_ids)
        cur.execute("DELETE FROM actions WHERE quarter=? AND report_type=? AND run_id=?", (quarter, report_type, run_id))
        cur.execute("DELETE FROM reports WHERE quarter=? AND report_type=? AND run_id=? AND file_name=?", (quarter, report_type, run_id, file_name))
        # Remove empty run records after the report-level delete.
        remaining = cur.execute("SELECT COUNT(*) FROM actions WHERE run_id=?", (run_id,)).fetchone()[0]
        if remaining == 0:
            cur.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
        deleted += 1
    con.commit(); con.close()
    log_audit("delete_report_files", f"Deleted {deleted} saved report file(s)")
    return deleted


def master_reset_uploaded_data(admin_password: str, phrase: str) -> Tuple[bool, str]:
    """Admin-only full reset of uploaded report/source data. Users remain intact."""
    if not is_admin():
        return False, "Only admins can perform a master reset."
    if not verify_current_admin_password(admin_password):
        return False, "Admin password incorrect. Nothing reset."
    if str(phrase).strip() != "MASTER RESET":
        return False, "Type MASTER RESET exactly to confirm."
    init_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    counts = {}
    for table in ["actions", "breaches", "runs", "reports", "service_master", "audit_logs"]:
        try:
            counts[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            cur.execute(f"DELETE FROM {table}")
        except Exception:
            counts[table] = "not found"
    con.commit(); con.close()
    # Clear all app state that can make old data look like it still exists.
    preserve = {"logged_in", "current_user", "auth_ok"}
    for k in list(st.session_state.keys()):
        if k not in preserve:
            del st.session_state[k]
    log_audit("master_reset", f"Master reset performed. Cleared: {counts}")
    return True, "Master reset complete. Uploaded data, service/provider source file, report history, and audit logs have been cleared. Users remain active."


def build_upload_review(uploaded_files: List, provider_rules) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Read all dropped files, identify quarter/report type, and prepare review table."""
    rows = []
    cache = {}
    seen_in_batch = set()
    for f in uploaded_files or []:
        try:
            txt = read_pdf_text(f)
            cache[f.name] = txt
            quarter = normalise_quarter_label(txt, f.name)
            report_type = detect_report_type(txt, f.name)
            existing = report_already_uploaded(quarter, report_type) if not quarter.startswith("UNIDENTIFIED") and not report_type.startswith("UNIDENTIFIED") else 0
            batch_key = (quarter, report_type)
            duplicate_in_batch = batch_key in seen_in_batch
            seen_in_batch.add(batch_key)
            if quarter.startswith("UNIDENTIFIED"):
                status = "Needs check — quarter not detected"
            elif report_type.startswith("UNIDENTIFIED"):
                status = "Needs check — report type not detected"
            elif duplicate_in_batch:
                status = "Duplicate in this upload batch"
            elif existing:
                status = f"Already uploaded — {existing} existing action rows"
            else:
                status = "Ready"
            rows.append({
                "File": f.name,
                "Detected quarter": quarter if not quarter.startswith("UNIDENTIFIED") else "— Select quarter —",
                "Detected report type": report_type if not report_type.startswith("UNIDENTIFIED") else "— Select report type —",
                "Existing rows": existing,
                "Status": status,
            })
        except Exception as e:
            rows.append({
                "File": getattr(f, "name", "Uploaded file"),
                "Detected quarter": "— Select quarter —",
                "Detected report type": "— Select report type —",
                "Existing rows": 0,
                "Status": f"Could not read PDF — {str(e)[:120]}",
            })
    return pd.DataFrame(rows), cache


def recalc_upload_review(edited_df: pd.DataFrame) -> pd.DataFrame:
    """Recalculate duplicate/existing statuses after an admin edits quarter/report-type dropdowns."""
    if edited_df is None or edited_df.empty:
        return pd.DataFrame()
    df = edited_df.copy()
    statuses = []
    existing_rows = []
    seen = set()
    for _, row in df.iterrows():
        quarter = str(row.get("Detected quarter", ""))
        report_type = str(row.get("Detected report type", ""))
        existing = report_already_uploaded(quarter, report_type) if quarter in quarter_options() and report_type in REPORT_TYPE_OPTIONS else 0
        key = (quarter, report_type)
        duplicate = key in seen
        seen.add(key)
        if quarter == "— Select quarter —" or quarter not in quarter_options():
            status = "Needs check — select quarter"
        elif report_type == "— Select report type —" or report_type not in REPORT_TYPE_OPTIONS:
            status = "Needs check — select report type"
        elif duplicate:
            status = "Duplicate in this upload batch"
        elif existing:
            status = f"Already uploaded — {existing} existing action rows"
        else:
            status = "Ready"
        statuses.append(status)
        existing_rows.append(existing)
    df["Existing rows"] = existing_rows
    df["Status"] = statuses
    return df




def _file_row_key(file_name: str) -> str:
    return hashlib.sha1(str(file_name).encode("utf-8")).hexdigest()[:12]


def remove_upload_file_from_review(fname: str):
    """Remove a file from the current upload review using a callback so the row disappears cleanly on the next rerun."""
    st.session_state.setdefault("upload_removed_files", [])
    if fname not in st.session_state["upload_removed_files"]:
        st.session_state["upload_removed_files"].append(fname)


def render_upload_review_editor(review_df: pd.DataFrame) -> pd.DataFrame:
    """Stable upload review editor: one compact table, changes applied in one submit to avoid Streamlit flicker."""
    if review_df is None or review_df.empty:
        return pd.DataFrame()

    upload_sig = "|".join(review_df["File"].astype(str).tolist())
    if st.session_state.get("upload_review_signature") != upload_sig:
        st.session_state["upload_review_signature"] = upload_sig
        st.session_state["upload_removed_files"] = []
        for f in review_df["File"].astype(str):
            rk = _file_row_key(f)
            st.session_state.pop(f"review_quarter_{rk}", None)
            st.session_state.pop(f"review_type_{rk}", None)
            st.session_state.pop(f"review_action_{rk}", None)

    removed = set(st.session_state.get("upload_removed_files", []))

    # Initialise row state from auto-detection.
    for _, row in review_df.iterrows():
        fname = str(row["File"])
        rk = _file_row_key(fname)
        q_key = f"review_quarter_{rk}"
        t_key = f"review_type_{rk}"
        a_key = f"review_action_{rk}"
        if q_key not in st.session_state:
            q_val = str(row.get("Detected quarter", "— Select quarter —"))
            st.session_state[q_key] = q_val if q_val in quarter_options() else "— Select quarter —"
        if t_key not in st.session_state:
            t_val = str(row.get("Detected report type", "— Select report type —"))
            st.session_state[t_key] = t_val if t_val in REPORT_TYPE_OPTIONS else "— Select report type —"
        if a_key not in st.session_state:
            st.session_state[a_key] = "Keep"

    def build_active_df() -> pd.DataFrame:
        rows = []
        for _, r in review_df.iterrows():
            fname = str(r["File"])
            if fname in set(st.session_state.get("upload_removed_files", [])):
                continue
            rk = _file_row_key(fname)
            rows.append({
                "File": fname,
                "Detected quarter": st.session_state.get(f"review_quarter_{rk}", "— Select quarter —"),
                "Detected report type": st.session_state.get(f"review_type_{rk}", "— Select report type —"),
                "Existing rows": int(r.get("Existing rows", 0) or 0),
                "Status": str(r.get("Status", "")),
            })
        if not rows:
            return pd.DataFrame(columns=["File","Detected quarter","Detected report type","Existing rows","Status"])
        return recalc_upload_review(pd.DataFrame(rows))

    active_df = build_active_df()

    st.markdown("""
    <div class='ya-review-shell ya-less-streamlit'>
      <div class='ya-review-intro'>
        <div class='ya-review-eyebrow'>Upload review</div>
        <div class='ya-review-copy'>Confirm the quarter and report type before processing. Make corrections here before saving. Use standard quarter labels and report types. Select Remove for files you do not want processed.</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Form = select/dropdown changes do not cause immediate reruns. Much closer to a real web-app workflow.
    with st.form("upload_review_stable_form", clear_on_submit=False):
        st.markdown("<div class='ya-review-table ya-review-table-stable'>", unsafe_allow_html=True)
        h1,h2,h3,h4,h5,h6 = st.columns([4.4, 2.55, 2.75, .9, 2.45, 1.35], vertical_alignment="center")
        with h1: st.markdown("<div class='ya-review-header'>File</div>", unsafe_allow_html=True)
        with h2: st.markdown("<div class='ya-review-header'>Quarter</div>", unsafe_allow_html=True)
        with h3: st.markdown("<div class='ya-review-header'>Report type</div>", unsafe_allow_html=True)
        with h4: st.markdown("<div class='ya-review-header'>Existing</div>", unsafe_allow_html=True)
        with h5: st.markdown("<div class='ya-review-header'>Status</div>", unsafe_allow_html=True)
        with h6: st.markdown("<div class='ya-review-header'>Action</div>", unsafe_allow_html=True)

        for i, row in active_df.iterrows():
            fname = str(row["File"])
            rk = _file_row_key(fname)
            status = str(row.get("Status", ""))
            existing = int(row.get("Existing rows", 0) or 0)
            status_class = "ready" if status.lower() == "ready" else ("duplicate" if existing or "Duplicate" in status else "check")
            file_display = fname if len(fname) <= 92 else fname[:58] + "…" + fname[-28:]

            st.markdown(f"<div class='ya-review-row {'last' if i == len(active_df)-1 else ''}'>", unsafe_allow_html=True)
            c1,c2,c3,c4,c5,c6 = st.columns([4.4, 2.55, 2.75, .9, 2.45, 1.35], vertical_alignment="center")
            with c1:
                st.markdown(f"<div class='ya-review-file' title='{fname}'><span class='ya-file-icon'>PDF</span>{file_display}</div>", unsafe_allow_html=True)
            with c2:
                current_q = st.session_state.get(f"review_quarter_{rk}", "— Select quarter —")
                q_opts = quarter_options()
                st.selectbox(
                    "Quarter",
                    q_opts,
                    index=q_opts.index(current_q) if current_q in q_opts else 0,
                    key=f"review_quarter_{rk}",
                    label_visibility="collapsed",
                )
            with c3:
                current_t = st.session_state.get(f"review_type_{rk}", "— Select report type —")
                st.selectbox(
                    "Report type",
                    REPORT_TYPE_OPTIONS,
                    index=REPORT_TYPE_OPTIONS.index(current_t) if current_t in REPORT_TYPE_OPTIONS else 0,
                    key=f"review_type_{rk}",
                    label_visibility="collapsed",
                )
            with c4:
                st.markdown(f"<div class='ya-review-existing'>{existing}</div>", unsafe_allow_html=True)
            with c5:
                st.markdown(f"<div class='ya-review-status-text {status_class}'>{status}</div>", unsafe_allow_html=True)
            with c6:
                st.selectbox(
                    "Action",
                    ["Keep", "Remove"],
                    index=0,
                    key=f"review_action_{rk}",
                    label_visibility="collapsed",
                )
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        f1, f2, f3 = st.columns([1.1, 1.1, 4])
        with f1:
            apply_clicked = st.form_submit_button("Apply review changes", type="primary")
        with f2:
            reset_removed_clicked = st.form_submit_button("Reset removed files")
        with f3:
            st.markdown("<div class='ya-form-hint'>Select Remove beside a file, then click Apply. Dropdowns will not refresh the page until you apply changes.</div>", unsafe_allow_html=True)

    if apply_clicked:
        new_removed = set(st.session_state.get("upload_removed_files", []))
        for _, r in review_df.iterrows():
            fname = str(r["File"])
            rk = _file_row_key(fname)
            if st.session_state.get(f"review_action_{rk}") == "Remove":
                new_removed.add(fname)
        st.session_state["upload_removed_files"] = sorted(new_removed)
        show_soft_loading("Please wait. Updating upload review...")
        st.rerun()

    if reset_removed_clicked:
        st.session_state["upload_removed_files"] = []
        show_soft_loading("Please wait. Restoring files...")
        st.rerun()

    if st.session_state.get("upload_removed_files"):
        st.markdown(f"<div class='ya-removed-note'>{len(st.session_state['upload_removed_files'])} file(s) removed from this upload consideration. Use Reset removed files to bring them back.</div>", unsafe_allow_html=True)

    return build_active_df()

def render_kpi_notes():
    st.markdown("""
    <div class='ya-note-grid'>
      <div class='ya-note-card'><h4>Actions</h4><p>Counts each published enforcement action row extracted from the uploaded NSW PDFs. This is not the same as breach references; one action can contain multiple Law/Reg items.</p></div>
      <div class='ya-note-card'><h4>Breach references</h4><p>Counts every Law or Regulation reference extracted from the reason field. This is the better measure for issue volume and complexity.</p></div>
      <div class='ya-note-card'><h4>L165/166/167</h4><p>Isolates the serious matters bucket: supervision, inappropriate discipline, and protection from harm/hazards.</p></div>
      <div class='ya-note-card'><h4>YA actions</h4><p>Counts Young Academics enforcement actions in the selected quarter range. This supports direct provider ranking.</p></div>
      <div class='ya-note-card'><h4>YA significant</h4><p>Counts Young Academics breach references that fall into Law 165, 166 or 167. This is the board-level risk indicator.</p></div>
    </div>
    """, unsafe_allow_html=True)


def rules_to_df(rules=DEFAULT_PROVIDER_RULES) -> pd.DataFrame:
    rows = []
    for provider, aliases in rules:
        for alias in aliases:
            rows.append({"provider": provider, "alias_contains": alias})
    return pd.DataFrame(rows)


def df_to_rules(df: pd.DataFrame) -> List[Tuple[str, List[str]]]:
    if df is None or df.empty:
        return DEFAULT_PROVIDER_RULES
    grouped: Dict[str, List[str]] = {}
    for _, r in df.dropna().iterrows():
        provider = str(r.get("provider", "")).strip()
        alias = str(r.get("alias_contains", "")).strip().lower()
        if provider and alias:
            grouped.setdefault(provider, []).append(alias)
    return list(grouped.items()) or DEFAULT_PROVIDER_RULES



def normalise_provider_stem(service_name: str) -> str:
    """Best-effort provider grouping when a service/centre is not in provider_mapping.csv."""
    name = re.sub(r"\s+", " ", str(service_name or "")).strip(" ,-–")
    if not name:
        return "Unknown / Needs Mapping"
    # Cut common location suffixes: Brand - Suburb, Brand – Suburb, Brand at School.
    name = re.split(r"\s+[–-]\s+", name)[0].strip()
    name = re.split(r"\s+at\s+", name, flags=re.I)[0].strip()
    # Remove common centre descriptor endings, but keep distinctive brands.
    name = re.sub(r"\b(Early Learning Centre|Early Learning|Childcare Centre|Child Care Centre|Long Day Care Centre|Preschool|Pre-School|Kindergarten|OSHC|OOSH)\b.*$", lambda m: m.group(0) if len(name.split()) <= 3 else "", name, flags=re.I).strip(" ,-–")
    # If still very long, keep a stable stem rather than suburb/address noise.
    words = name.split()
    if len(words) > 5:
        name = " ".join(words[:5])
    return name[:70] if name else "Unknown / Needs Mapping"

def looks_like_action_text(raw: str) -> bool:
    """Detect rows where PDF text extraction put action/reason text into the provider column."""
    cleaned = re.sub(r"\s+", " ", str(raw or "")).strip(" -,;:")
    low = cleaned.lower()
    if not cleaned:
        return True
    bad_bits = [
        "compliance notice", "compliance due", "due to non-compliance", "due to non compliance",
        "compliance due to", "compliance due", "compliance notice due", "non-compliance with the national",
        "national law", "national regulations", "emergency action", "emergency an education", "emergency an education and care",
        "enforceable undertaking", "enforceable due", "section 177", "section 179", "section 179a",
        "provider approval cancelled", "service approval", "service suspended", "grounds for",
        "regulatory authority", "offence to", "offence relating", "continued provision",
        "an education and care service", "immediate risk", "non-compliance posed", "children's health",
        "cancelled under", "decision to cancel", "the approved provider", "the regulatory authority"
    ]
    if any(bit in low for bit in bad_bits):
        return True
    if re.search(r"\b(law|regulation|section)\s*\d", low):
        return True
    if len(cleaned) > 85:
        return True
    return False


def clean_provider_name(raw: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(raw or "")).strip(" -,;:")
    if looks_like_action_text(cleaned):
        return "Unknown / Needs Mapping"
    return cleaned or "Unknown / Needs Mapping"


def infer_provider(text: str, rules: List[Tuple[str, List[str]]]) -> str:
    t = re.sub(r"\s+", " ", text.lower())
    for provider, aliases in rules:
        for alias in aliases:
            if alias.lower() in t:
                return provider
    first = text.strip().split("\n")[0]
    first = re.sub(r"\b\d{1,4}[A-Za-z]?\b.*", "", first).strip(" -,")
    return clean_provider_name(first[:80])


def detect_action_type(text: str, report_type: str) -> str:
    low = text.lower()
    if "involuntary" in report_type.lower() or "suspended under section 72" in low:
        return "Involuntary suspension"
    if "service approval" in report_type.lower() and "cancel" in low:
        return "Service approval cancellation"
    if "provider approval" in report_type.lower() and "cancel" in low:
        return "Provider approval cancellation"
    if "emergency action" in low or "section 179" in low:
        return "Emergency action notice"
    if "enforceable undertaking" in low or "179a" in low:
        return "Enforceable undertaking"
    if "compliance notice" in low or "section 177" in low:
        return "Compliance notice"
    return report_type


def extract_reason_section(block: str) -> str:
    m = DATE_RE.search(block)
    section = block[m.end():] if m else block
    stop_words = ["Issue of compliance notice", "Issue of emergency action", "Enter into an Enforceable", "Service approval suspended", "Cancellation of"]
    idxs = [section.lower().find(w.lower()) for w in stop_words if section.lower().find(w.lower()) >= 0]
    if idxs:
        section = section[:min(idxs)]
    return section


def extract_breaches(reason: str) -> List[Tuple[str, str, str]]:
    out = []
    for m in LAW_RE.finditer(reason):
        code = m.group(1).upper()
        if code in {"177", "179"}:
            continue
        classification = "Significant matter: Law 165/166/167" if code in SIGNIFICANT_LAWS else "Other Law/Reg breach"
        out.append((f"Law {code}", "Law", classification))
    for m in REG_RE.finditer(reason):
        code = m.group(1).upper()
        out.append((f"Regulation {code}", "Regulation", "Other Law/Reg breach"))
    return out


def split_blocks(text: str) -> List[str]:
    matches = list(ID_RE.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append(text[start:end].strip())
    return blocks


def _clean_cell(value) -> str:
    """Normalise a PDF table cell into compact text."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalise_header(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _find_header_row(table: list) -> int:
    """Find the row that contains the PDF table headers."""
    for i, row in enumerate(table[:6]):
        joined = " ".join(_clean_cell(c).lower() for c in row)
        has_id = "service id" in joined or "provider id" in joined or "serviceid" in joined or "providerid" in joined
        has_name = "service name" in joined or "provider name" in joined or "servicename" in joined or "providername" in joined
        has_date = "date issued" in joined or "dateissued" in joined
        if has_id and has_name and has_date:
            return i
    return -1


def _column_index(headers: list, candidates: list) -> int:
    normalised = [_normalise_header(h) for h in headers]
    for cand in candidates:
        c = _normalise_header(cand)
        for i, h in enumerate(normalised):
            if c == h or c in h or h in c:
                return i
    return -1


def extract_pdf_table_records(uploaded_file, quarter: str, report_type: str, provider_rules, run_id: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Extract actions/breaches from structured PDF tables before falling back to text blocks.

    This fixes the previous issue where the parser split on Service ID and accidentally
    treated the reason/action text as the service/provider name. The NSW PDFs contain
    explicit columns such as Service name, Service ID, Reason for enforcement action,
    Date issued and Details of action taken, so use those columns when available.
    """
    if pdfplumber is None:
        return pd.DataFrame(), pd.DataFrame()

    try:
        data = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

    action_rows, breach_rows = [], []
    processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    seq = 0

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    header_idx = _find_header_row(table)
                    if header_idx < 0:
                        continue
                    headers = [_clean_cell(c) for c in table[header_idx]]
                    rows = table[header_idx + 1:]

                    id_idx = _column_index(headers, ["Service ID", "Provider ID"])
                    service_name_idx = _column_index(headers, ["Service name", "Provider name"])
                    address_idx = _column_index(headers, ["Service address", "Address"])
                    date_idx = _column_index(headers, ["Date issued"])
                    nature_idx = _column_index(headers, ["Nature of enforcement action", "Nature of enforcement action issued"])
                    reason_idx = _column_index(headers, ["Reason for enforcement action", "Grounds for decision to cancel", "Grounds for involuntary suspension"])
                    details_idx = _column_index(headers, ["Details of action taken"])

                    if id_idx < 0 or service_name_idx < 0:
                        continue

                    current = None
                    for row in rows:
                        # Pad short rows so indexing is safe.
                        row = list(row) + [""] * max(0, len(headers) - len(row))
                        entity_id = _clean_cell(row[id_idx]) if id_idx >= 0 else ""
                        service_name = _clean_cell(row[service_name_idx]) if service_name_idx >= 0 else ""
                        address = _clean_cell(row[address_idx]) if address_idx >= 0 else ""
                        date_issued = _clean_cell(row[date_idx]) if date_idx >= 0 else ""
                        nature = _clean_cell(row[nature_idx]) if nature_idx >= 0 else ""
                        reason = _clean_cell(row[reason_idx]) if reason_idx >= 0 else ""
                        details = _clean_cell(row[details_idx]) if details_idx >= 0 else ""

                        # Continuation rows often have blank ID/name and extra reason text.
                        if not entity_id and current:
                            extra_text = " ".join(x for x in [service_name, address, nature, reason, details] if x)
                            current["raw_text"] = (current.get("raw_text", "") + " " + extra_text).strip()[:4000]
                            current["reason_text"] = (current.get("reason_text", "") + " " + extra_text).strip()
                            continue

                        if not ID_RE.search(entity_id):
                            continue

                        seq += 1
                        entity_id = ID_RE.search(entity_id).group(1)
                        row_text = " ".join(x for x in [entity_id, service_name, address, nature, reason, date_issued, details] if x)
                        provider_seed = service_name or reason or row_text
                        provider = infer_provider(provider_seed, provider_rules)
                        if looks_like_action_text(provider):
                            provider = normalise_provider_stem(service_name) if service_name else "Unknown / Needs Mapping"

                        action_id = f"{run_id}-{report_type[:3]}-{seq:04d}"
                        reason_text = " ".join(x for x in [nature, reason, details] if x)
                        breaches = extract_breaches(reason_text)
                        action_type = detect_action_type(row_text, report_type)

                        current = {
                            "run_id": run_id,
                            "quarter": quarter,
                            "report_type": report_type,
                            "action_id": action_id,
                            "entity_id": entity_id,
                            "provider": provider,
                            "service_name": service_name or provider,
                            "date_issued": date_issued,
                            "action_type": action_type,
                            "raw_text": row_text[:4000],
                            "reason_text": reason_text,
                            "processed_at": processed_at,
                        }
                        action_rows.append(current)
                        for code, family, classification in breaches:
                            breach_rows.append({
                                "run_id": run_id,
                                "quarter": quarter,
                                "action_id": action_id,
                                "provider": provider,
                                "breach_code": code,
                                "breach_family": family,
                                "classification": classification,
                                "processed_at": processed_at,
                            })
    except Exception:
        uploaded_file.seek(0)
        return pd.DataFrame(), pd.DataFrame()

    uploaded_file.seek(0)
    return pd.DataFrame(action_rows), pd.DataFrame(breach_rows)


def parse_pdf(uploaded_file, quarter: str, report_type: str, provider_rules, run_id: str = None, pre_read_text: str = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Parse one NSW enforcement PDF.

    Primary path: structured PDF table extraction, which correctly captures Service name / Provider name.
    Fallback path: text block extraction for odd PDFs where tables are not extractable.
    """
    run_id = run_id or datetime.now().strftime("%Y%m%d%H%M%S")

    # First try structured table extraction. This is much more reliable for service_name.
    table_actions, table_breaches = extract_pdf_table_records(uploaded_file, quarter, report_type, provider_rules, run_id)
    if table_actions is not None and not table_actions.empty:
        return table_actions, table_breaches

    # Fallback for PDFs where pdfplumber cannot read the table grid.
    text = pre_read_text if pre_read_text is not None else read_pdf_text(uploaded_file)
    blocks = split_blocks(text)
    processed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    action_rows, breach_rows = [], []
    for idx, block in enumerate(blocks, start=1):
        id_match = ID_RE.search(block)
        date_match = DATE_RE.search(block)
        if not id_match:
            continue
        entity_id = id_match.group(1)
        date_issued = date_match.group(1) if date_match else ""

        # Fallback only: attempt to infer a sane display name. If it looks like action text,
        # keep it unmapped rather than polluting provider tables.
        left = block[id_match.end(): date_match.start() if date_match else min(len(block), 220)].strip()
        service_name = re.sub(r"\s+", " ", left).strip()[:180]
        if looks_like_action_text(service_name):
            service_name = ""
        provider = infer_provider((service_name or "") + "\n" + block[:400], provider_rules)
        if looks_like_action_text(provider):
            provider = normalise_provider_stem(service_name) if service_name else "Unknown / Needs Mapping"

        action_id = f"{run_id}-{report_type[:3]}-{idx:04d}"
        reason = extract_reason_section(block)
        breaches = extract_breaches(reason)
        action_rows.append({
            "run_id": run_id,
            "quarter": quarter,
            "report_type": report_type,
            "action_id": action_id,
            "entity_id": entity_id,
            "provider": provider,
            "service_name": service_name,
            "date_issued": date_issued,
            "action_type": detect_action_type(block, report_type),
            "raw_text": block[:4000],
            "processed_at": processed_at,
        })
        for code, family, classification in breaches:
            breach_rows.append({
                "run_id": run_id,
                "quarter": quarter,
                "action_id": action_id,
                "provider": provider,
                "breach_code": code,
                "breach_family": family,
                "classification": classification,
                "processed_at": processed_at,
            })
    return pd.DataFrame(action_rows), pd.DataFrame(breach_rows)


def make_provider_summary(actions: pd.DataFrame, breaches: pd.DataFrame, quarters: List[str] = None, top_n: int = None) -> pd.DataFrame:
    if actions.empty:
        return pd.DataFrame()
    a = actions.copy()
    b = breaches.copy()
    if quarters:
        a = a[a["quarter"].isin(quarters)]
        b = b[b["quarter"].isin(quarters)] if not b.empty else b
    action_counts = a.groupby("provider").size().rename("Enforcement Actions")
    if not b.empty:
        piv = b.pivot_table(index="provider", columns="classification", values="breach_code", aggfunc="count", fill_value=0)
    else:
        piv = pd.DataFrame(index=action_counts.index)
    for col in ["Significant matter: Law 165/166/167", "Other Law/Reg breach"]:
        if col not in piv.columns:
            piv[col] = 0
    out = pd.concat([action_counts, piv], axis=1).fillna(0)
    out = out.rename(columns={"Significant matter: Law 165/166/167": "L165/166/167", "Other Law/Reg breach": "Other"})
    out["Total Breach References"] = out["L165/166/167"] + out["Other"]
    out = out.reset_index().sort_values(["Enforcement Actions", "Total Breach References"], ascending=False)
    out.insert(0, "Rank", range(1, len(out) + 1))
    if top_n:
        ya = out[out["provider"].eq("Young Academics")]
        top = out.head(top_n)
        out = pd.concat([top, ya]).drop_duplicates(subset=["provider"]).sort_values("Rank")
    return out


def make_law_summary(breaches: pd.DataFrame) -> pd.DataFrame:
    if breaches.empty:
        return pd.DataFrame(columns=["breach_code", "Count"])
    return breaches.groupby("breach_code").size().reset_index(name="Count").sort_values("Count", ascending=False)


def quarter_summary(actions: pd.DataFrame, breaches: pd.DataFrame) -> pd.DataFrame:
    if actions.empty:
        return pd.DataFrame()
    action_q = actions.groupby("quarter").size().rename("Enforcement Actions")
    if breaches.empty:
        out = action_q.reset_index()
        out["L165/166/167"] = 0
        out["Other"] = 0
        out["Total Breach References"] = 0
        return out
    b = breaches.pivot_table(index="quarter", columns="classification", values="breach_code", aggfunc="count", fill_value=0)
    for col in ["Significant matter: Law 165/166/167", "Other Law/Reg breach"]:
        if col not in b.columns:
            b[col] = 0
    out = pd.concat([action_q, b], axis=1).fillna(0).reset_index()
    out = out.rename(columns={"Significant matter: Law 165/166/167": "L165/166/167", "Other Law/Reg breach": "Other"})
    out["Total Breach References"] = out["L165/166/167"] + out["Other"]
    return out



def quarter_sort_key(label: str):
    """Sort labels like Q1 FY25/26 — Jul–Sep 2025 in true financial-year order."""
    txt = str(label or "")
    m = re.search(r"Q([1-4])\s+FY(\d{2})/(\d{2})", txt)
    if not m:
        return (9999, 9, txt)
    q = int(m.group(1))
    fy_start = 2000 + int(m.group(2))
    return (fy_start, q, txt)


def sorted_quarter_list(df: pd.DataFrame) -> List[str]:
    if df is None or df.empty or "quarter" not in df.columns:
        return []
    return sorted([str(q) for q in df["quarter"].dropna().unique().tolist()], key=quarter_sort_key)


def add_total_col(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    numeric_cols = [c for c in out.columns if c != out.columns[0] and pd.api.types.is_numeric_dtype(out[c])]
    if numeric_cols:
        out["All time total"] = out[numeric_cols].sum(axis=1)
    return out


def make_provider_pivot(actions: pd.DataFrame, breaches: pd.DataFrame, metric: str = "Actions", quarters: List[str] = None) -> pd.DataFrame:
    """Provider rows, quarter columns. Much easier to read than long linear QoQ tables."""
    if actions is None or actions.empty:
        return pd.DataFrame()
    qs = quarters or sorted_quarter_list(actions)
    if metric == "Actions":
        base = actions[actions["quarter"].isin(qs)] if qs else actions.copy()
        piv = base.pivot_table(index="provider", columns="quarter", values="action_id", aggfunc="count", fill_value=0)
    else:
        if breaches is None or breaches.empty:
            return pd.DataFrame()
        base = breaches[breaches["quarter"].isin(qs)] if qs else breaches.copy()
        if metric == "Significant matters":
            base = base[base["classification"].eq("Significant matter: Law 165/166/167")]
        elif metric == "Other breaches":
            base = base[base["classification"].eq("Other Law/Reg breach")]
        piv = base.pivot_table(index="provider", columns="quarter", values="breach_code", aggfunc="count", fill_value=0)
    for q in qs:
        if q not in piv.columns:
            piv[q] = 0
    piv = piv[qs] if qs else piv
    piv = piv.reset_index()
    piv = add_total_col(piv)
    if "All time total" in piv.columns:
        piv = piv.sort_values("All time total", ascending=False)
    return piv


def make_issue_pivot(breaches: pd.DataFrame, issue_col: str = "breach_code", quarters: List[str] = None) -> pd.DataFrame:
    if breaches is None or breaches.empty:
        return pd.DataFrame()
    qs = quarters or sorted_quarter_list(breaches)
    base = breaches[breaches["quarter"].isin(qs)] if qs else breaches.copy()
    piv = base.pivot_table(index=issue_col, columns="quarter", values="action_id", aggfunc="count", fill_value=0).reset_index()
    for q in qs:
        if q not in piv.columns:
            piv[q] = 0
    cols = [issue_col] + qs
    piv = piv[cols]
    piv = add_total_col(piv)
    if "All time total" in piv.columns:
        piv = piv.sort_values("All time total", ascending=False)
    return piv


def make_action_type_pivot(actions: pd.DataFrame, quarters: List[str] = None) -> pd.DataFrame:
    if actions is None or actions.empty:
        return pd.DataFrame()
    qs = quarters or sorted_quarter_list(actions)
    base = actions[actions["quarter"].isin(qs)] if qs else actions.copy()
    piv = base.pivot_table(index="action_type", columns="quarter", values="action_id", aggfunc="count", fill_value=0).reset_index()
    for q in qs:
        if q not in piv.columns:
            piv[q] = 0
    piv = piv[["action_type"] + qs]
    piv = add_total_col(piv)
    if "All time total" in piv.columns:
        piv = piv.sort_values("All time total", ascending=False)
    return piv


def make_auto_mapping_suggestions(actions: pd.DataFrame, rules: List[Tuple[str, List[str]]]) -> pd.DataFrame:
    """Show provider groups that were not explicitly covered by provider_mapping.csv."""
    if actions is None or actions.empty:
        return pd.DataFrame(columns=["provider", "suggested_alias_contains", "actions", "sample_service"])
    mapped_providers = {p for p, _aliases in rules}
    df = actions.copy()
    unknown = df[~df["provider"].isin(mapped_providers)].copy()
    if unknown.empty:
        return pd.DataFrame(columns=["provider", "suggested_alias_contains", "actions", "sample_service"])
    rows = []
    for provider, g in unknown.groupby("provider"):
        provider_txt = str(provider).strip()
        if not provider_txt or provider_txt.lower().startswith("unknown"):
            sample = str(g["service_name"].dropna().iloc[0]) if not g["service_name"].dropna().empty else provider_txt
            alias = normalise_provider_stem(sample).lower()
        else:
            alias = provider_txt.lower()
        rows.append({
            "provider": provider_txt,
            "suggested_alias_contains": alias,
            "actions": len(g),
            "sample_service": str(g["service_name"].dropna().iloc[0]) if not g["service_name"].dropna().empty else "",
        })
    return pd.DataFrame(rows).sort_values("actions", ascending=False)

def ya_position_text(summary: pd.DataFrame) -> str:
    if summary.empty or "Young Academics" not in set(summary["provider"]):
        return "Young Academics does not appear in the selected report set."
    row = summary[summary["provider"].eq("Young Academics")].iloc[0]
    return f"YA Rank: {int(row['Rank'])}/{len(summary)} • Actions: {int(row['Enforcement Actions'])} • L165/166/167: {int(row['L165/166/167'])} • Other: {int(row['Other'])}"


def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#357b84", "font_color": "#FFFFFF", "border": 1})
        ya_fmt = workbook.add_format({"bold": True, "bg_color": "#FFF200", "font_color": "#000000"})
        for name, df in sheets.items():
            safe = name[:31].replace("/", "-")
            df.to_excel(writer, sheet_name=safe, index=False)
            ws = writer.sheets[safe]
            for i, col in enumerate(df.columns):
                width = min(max(len(str(col)) + 4, 13), 48)
                ws.set_column(i, i, width)
                ws.write(0, i, col, header_fmt)
            if "provider" in df.columns:
                provider_col = list(df.columns).index("provider")
                for r, val in enumerate(df["provider"], start=1):
                    if val == "Young Academics":
                        ws.set_row(r, None, ya_fmt)
    return output.getvalue()



def exportable_table(title: str, df: pd.DataFrame, key: str, file_prefix: str = None, caption: str = None):
    """Render a table with its own CSV export button."""
    st.markdown(f"### {title}")
    if caption:
        st.caption(caption)
    if df is None or df.empty:
        st.info("No rows for the current selection.")
        return
    st.dataframe(df, use_container_width=True, hide_index=True, key=f"table_{key}")
    clean_prefix = file_prefix or title.lower()
    clean_prefix = re.sub(r"[^a-z0-9]+", "_", clean_prefix.lower()).strip("_") or "table"
    st.download_button(
        f"Download {title} CSV",
        df.to_csv(index=False).encode("utf-8"),
        f"{clean_prefix}.csv",
        "text/csv",
        key=f"download_{key}",
    )


def render_quarter_selector(quarters_all: List[str]) -> List[str]:
    """Clickable quarter chips/check boxes rather than a cramped multiselect."""
    if not quarters_all:
        return []
    st.markdown("### Report controls")
    use_all_quarters = st.checkbox("Use all uploaded quarters", value=True, key="use_all_uploaded_quarters_v40")
    if use_all_quarters:
        st.markdown(f"<span class='ya-pill'>All-time view active: {len(quarters_all)} quarters selected</span>", unsafe_allow_html=True)
        return quarters_all

    st.caption("Click quarters on/off to include or remove them from the report.")
    selected = []
    cols = st.columns(min(4, max(1, len(quarters_all))))
    for i, q in enumerate(quarters_all):
        with cols[i % len(cols)]:
            default = bool(st.session_state.get(f"quarter_chip_{i}_{q}", i < 4))
            if st.checkbox(q, value=default, key=f"quarter_chip_{i}_{q}"):
                selected.append(q)
    if not selected:
        st.warning("Select at least one quarter to populate the dashboard.")
    return selected

def render_header():
    st.markdown(f"""
    <div class='ya-shell'>
      <div class='ya-header'>
        <div class='ya-brand'>
          <img class='ya-logo' src='{LOGO_URL}' />
          <div class='ya-title'>
            <h1>{APP_TITLE}</h1>
            <p>Register of Published Enforcement Actions Benchmarking</p>
            <p><strong>Developed by James Maclean-Horton</strong></p>
          </div>
        </div>
        <div class='ya-version'>{APP_VERSION}</div>
      </div>
      <div class='ya-note'>Internal reporting tool for quarterly NSW enforcement action PDFs, provider benchmarking, Law 165/166/167 split, cancellations, suspensions, and rolling history.</div>
      <div class='ya-disclaimer'>This system and its outputs are the property of Young Academics Early Learning Centre. Any unauthorised access, use, copying, distribution, or disclosure is strictly prohibited.</div>
    </div>
    """, unsafe_allow_html=True)



def add_percent(df: pd.DataFrame, count_col: str = "Count") -> pd.DataFrame:
    if df is None or df.empty or count_col not in df.columns:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    total = float(out[count_col].sum() or 0)
    out["%"] = (out[count_col] / total * 100).round(1) if total else 0.0
    return out


def make_action_category_summary(actions: pd.DataFrame, quarter: str = None) -> pd.DataFrame:
    if actions.empty:
        return pd.DataFrame(columns=["Category", "Count", "%"])
    df = actions.copy()
    if quarter:
        df = df[df["quarter"].eq(quarter)]
    if df.empty:
        return pd.DataFrame(columns=["Category", "Count", "%"])
    out = df.groupby("action_type").size().reset_index(name="Count").rename(columns={"action_type":"Category"}).sort_values("Count", ascending=False)
    return add_percent(out)


def make_breach_category_summary(breaches: pd.DataFrame, quarter: str = None) -> pd.DataFrame:
    if breaches.empty:
        return pd.DataFrame(columns=["Category", "Count", "%"])
    df = breaches.copy()
    if quarter:
        df = df[df["quarter"].eq(quarter)]
    if df.empty:
        return pd.DataFrame(columns=["Category", "Count", "%"])
    out = df.groupby("classification").size().reset_index(name="Count").rename(columns={"classification":"Category"}).sort_values("Count", ascending=False)
    return add_percent(out)


def _clean_provider_table_source(df: pd.DataFrame) -> pd.DataFrame:
    """Remove parser leakage from provider-level reporting tables.

    These rows are still counted in global totals, but not shown as named competitors.
    They appear in the mapping gaps panel instead.
    """
    if df is None or df.empty or "provider" not in df.columns:
        return pd.DataFrame() if df is None else df
    out = df.copy()
    out["provider"] = out["provider"].astype(str).str.strip()
    bad = out["provider"].apply(lambda x: looks_like_action_text(x) or x in ["", "Unknown", "Unknown / Needs Mapping"])
    return out[~bad].copy()


def make_provider_action_category_summary(actions: pd.DataFrame, quarter: str = None) -> pd.DataFrame:
    if actions.empty:
        return pd.DataFrame(columns=["provider", "Category", "Count", "% of Category", "% of Provider Actions"])
    df = _clean_provider_table_source(actions)
    if quarter:
        df = df[df["quarter"].eq(quarter)]
    if df.empty:
        return pd.DataFrame(columns=["provider", "Category", "Count", "% of Category", "% of Provider Actions"])
    out = df.groupby(["provider", "action_type"]).size().reset_index(name="Count").rename(columns={"action_type":"Category"})
    cat_total = out.groupby("Category")["Count"].transform("sum")
    prov_total = out.groupby("provider")["Count"].transform("sum")
    out["% of Category"] = (out["Count"] / cat_total * 100).round(1)
    out["% of Provider Actions"] = (out["Count"] / prov_total * 100).round(1)
    return out.sort_values(["Category", "Count"], ascending=[True, False])


def make_provider_breach_category_summary(breaches: pd.DataFrame, quarter: str = None) -> pd.DataFrame:
    if breaches.empty:
        return pd.DataFrame(columns=["provider", "Category", "Count", "% of Category", "% of Provider Breaches"])
    df = _clean_provider_table_source(breaches)
    if quarter:
        df = df[df["quarter"].eq(quarter)]
    if df.empty:
        return pd.DataFrame(columns=["provider", "Category", "Count", "% of Category", "% of Provider Breaches"])
    out = df.groupby(["provider", "classification"]).size().reset_index(name="Count").rename(columns={"classification":"Category"})
    cat_total = out.groupby("Category")["Count"].transform("sum")
    prov_total = out.groupby("provider")["Count"].transform("sum")
    out["% of Category"] = (out["Count"] / cat_total * 100).round(1)
    out["% of Provider Breaches"] = (out["Count"] / prov_total * 100).round(1)
    return out.sort_values(["Category", "Count"], ascending=[True, False])


def make_compliance_position_table(breaches: pd.DataFrame, provider_col: str = "provider") -> pd.DataFrame:
    """Board-style table: Provider | Law 165/166/167 | Other | Total."""
    cols = ["Provider", "Law 165/166/167", "Other", "Total"]
    if breaches is None or breaches.empty or provider_col not in breaches.columns:
        return pd.DataFrame(columns=cols)
    df = _clean_provider_table_source(breaches.rename(columns={provider_col: "provider"}))
    if df.empty:
        return pd.DataFrame(columns=cols)
    piv = df.pivot_table(index="provider", columns="classification", values="breach_code", aggfunc="count", fill_value=0)
    sig_col = "Significant matter: Law 165/166/167"
    other_col = "Other Law/Reg breach"
    for c in [sig_col, other_col]:
        if c not in piv.columns:
            piv[c] = 0
    out = piv[[sig_col, other_col]].reset_index().rename(columns={"provider":"Provider", sig_col:"Law 165/166/167", other_col:"Other"})
    out["Total"] = out["Law 165/166/167"] + out["Other"]
    return out.sort_values(["Total", "Law 165/166/167"], ascending=False).reset_index(drop=True)


def make_mapping_gaps(actions: pd.DataFrame) -> pd.DataFrame:
    if actions is None or actions.empty:
        return pd.DataFrame(columns=["entity_id", "service_name", "raw_provider", "quarter", "Count"])
    df = actions.copy()
    raw_provider = df.get("provider", pd.Series([""]*len(df))).astype(str)
    bad = raw_provider.apply(lambda x: looks_like_action_text(x) or x in ["", "Unknown", "Unknown / Needs Mapping"])
    gaps = df[bad].copy()
    if gaps.empty:
        return pd.DataFrame(columns=["entity_id", "service_name", "raw_provider", "quarter", "Count"])
    gaps["raw_provider"] = raw_provider[bad].values
    cols = [c for c in ["entity_id", "service_name", "raw_provider", "quarter"] if c in gaps.columns]
    return gaps.groupby(cols, dropna=False).size().reset_index(name="Count").sort_values("Count", ascending=False)


def make_provider_qoq_summary(actions: pd.DataFrame, breaches: pd.DataFrame) -> pd.DataFrame:
    if actions.empty:
        return pd.DataFrame()
    rows = []
    for (quarter, provider), a in actions.groupby(["quarter", "provider"]):
        b = breaches[(breaches["quarter"].eq(quarter)) & (breaches["provider"].eq(provider))] if not breaches.empty else pd.DataFrame()
        sig = int((b["classification"].eq("Significant matter: Law 165/166/167")).sum()) if not b.empty else 0
        rows.append({
            "quarter": quarter,
            "provider": provider,
            "Enforcement Actions": len(a),
            "Breach References": len(b),
            "L165/166/167": sig,
            "Other": max(len(b) - sig, 0),
        })
    out = pd.DataFrame(rows).sort_values(["provider", "quarter"])
    out["QoQ Action Change"] = out.groupby("provider")["Enforcement Actions"].diff().fillna(0).astype(int)
    out["QoQ Breach Change"] = out.groupby("provider")["Breach References"].diff().fillna(0).astype(int)
    return out


def make_type_qoq_summary(actions: pd.DataFrame, breaches: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    action_qoq = pd.DataFrame()
    breach_qoq = pd.DataFrame()
    if not actions.empty:
        action_qoq = actions.groupby(["quarter", "provider", "action_type"]).size().reset_index(name="Count")
        action_qoq = action_qoq.sort_values(["provider", "action_type", "quarter"])
        action_qoq["QoQ Change"] = action_qoq.groupby(["provider", "action_type"])["Count"].diff().fillna(0).astype(int)
    if not breaches.empty:
        breach_qoq = breaches.groupby(["quarter", "provider", "classification"]).size().reset_index(name="Count")
        breach_qoq = breach_qoq.rename(columns={"classification":"Category"}).sort_values(["provider", "Category", "quarter"])
        breach_qoq["QoQ Change"] = breach_qoq.groupby(["provider", "Category"])["Count"].diff().fillna(0).astype(int)
    return action_qoq, breach_qoq


def render_pie(df: pd.DataFrame, title: str, key: str = None):
    if df.empty or df["Count"].sum() == 0:
        st.info(f"No data available for {title.lower()}.")
        return
    plot_df = add_percent(df)
    fig = px.pie(
        plot_df,
        names="Category",
        values="Count",
        hole=0.62,
        color_discrete_sequence=["#8edfe4", "#08245c", "#fff200", "#f59f9c", "#54b9a8", "#d6f3f5", "#4b9ca4"],
        custom_data=["%"] if "%" in plot_df.columns else None,
    )
    fig.update_traces(
        textposition="inside",
        textinfo="percent",
        hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Share: %{percent}<extra></extra>",
        marker=dict(line=dict(color="rgba(255,255,255,.72)", width=2)),
    )
    fig.update_layout(
        height=355,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ffffff", family="Inter, Arial"),
        legend=dict(orientation="v", yanchor="middle", y=.5, xanchor="left", x=.98, font=dict(color="#ffffff", size=12), title=dict(text="Category", font=dict(color="#d8f4f6"))),
        showlegend=True,
    )
    st.markdown(f"<div class='ya-dashboard-card'><h3>{title}</h3><div class='ya-chart-caption'>Includes count and percentage share for the selected quarter.</div>", unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, key=key)
    st.markdown("</div>", unsafe_allow_html=True)


def provider_detail_view(provider: str, actions: pd.DataFrame, breaches: pd.DataFrame, selected_quarters: List[str]):
    st.button("← Back to dashboard", on_click=lambda: st.session_state.pop("provider_detail", None))
    a = actions[actions["provider"].eq(provider)].copy()
    b = breaches[breaches["provider"].eq(provider)].copy() if not breaches.empty else breaches
    if selected_quarters:
        a = a[a["quarter"].isin(selected_quarters)]
        b = b[b["quarter"].isin(selected_quarters)] if not b.empty else b

    st.markdown(f"""
    <div class='ya-provider-title'>
      <h1>{provider}</h1>
      <p>Provider summary across selected quarters: <strong>{', '.join(selected_quarters) if selected_quarters else 'All history'}</strong></p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Actions", f"{len(a):,}")
    c2.metric("Breach references", f"{len(b):,}")
    sig = int((b["classification"] == "Significant matter: Law 165/166/167").sum()) if not b.empty else 0
    c3.metric("L165/166/167", f"{sig:,}")
    c4.metric("Other", f"{(len(b)-sig):,}")

    st.markdown("<div class='ya-white-panel'><h3>Executive summary</h3>", unsafe_allow_html=True)
    if a.empty:
        st.markdown("<p>No enforcement actions found for this provider in the selected period.</p></div>", unsafe_allow_html=True)
        return
    top_action = a["action_type"].mode().iloc[0] if not a["action_type"].dropna().empty else "Not available"
    top_breach = b["breach_code"].mode().iloc[0] if not b.empty and not b["breach_code"].dropna().empty else "No breach references extracted"
    q_count = a["quarter"].nunique()
    st.markdown(f"""
    <p><strong>{provider}</strong> appears in <strong>{len(a):,}</strong> enforcement action row(s) across <strong>{q_count}</strong> selected quarter(s).</p>
    <p>The most common action category is <strong>{top_action}</strong>. The most common extracted Law/Reg reference is <strong>{top_breach}</strong>.</p>
    <p>Serious matter references under Law 165/166/167 total <strong>{sig:,}</strong>, with all other extracted Law/Reg references totalling <strong>{(len(b)-sig):,}</strong>.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### Provider dashboard")
    p1, p2 = st.columns(2)
    with p1:
        render_pie(make_action_category_summary(a), "Actions by category", key=f"provider_actions_pie_{provider}")
    with p2:
        render_pie(make_breach_category_summary(b), "Breach references by category", key=f"provider_breaches_pie_{provider}")

    st.markdown("### Quarter trend")
    pq = quarter_summary(a, b)
    st.dataframe(pq, use_container_width=True, hide_index=True, key=f"provider_qtrend_{provider}")
    if not pq.empty:
        st.line_chart(pq.set_index("quarter")[["Enforcement Actions", "L165/166/167", "Other"]])

    st.markdown("### Action category breakdown")
    st.dataframe(make_action_category_summary(a), use_container_width=True, hide_index=True, key=f"provider_action_cat_{provider}")

    st.markdown("### Law/Reg references")
    st.dataframe(make_law_summary(b), use_container_width=True, hide_index=True, key=f"provider_law_summary_{provider}")

    st.markdown("### Service/action level detail")
    display_cols = ["quarter", "report_type", "entity_id", "service_name", "date_issued", "action_type"]
    st.dataframe(a[display_cols], use_container_width=True, hide_index=True, key=f"provider_detail_rows_{provider}")

    with st.expander("Show raw extracted text excerpts", expanded=False):
        for _, row in a.head(30).iterrows():
            st.markdown(f"**{row.get('date_issued','')} — {row.get('service_name','')} — {row.get('action_type','')}**")
            st.code(str(row.get("raw_text", ""))[:2500])



def render_upload_delete_page(hist_actions: pd.DataFrame, hist_breaches: pd.DataFrame, runs: pd.DataFrame):
    st.markdown("<div class='ya-section-card'>", unsafe_allow_html=True)
    st.markdown("<div class='ya-panel-title'>Upload / Delete Files</div>", unsafe_allow_html=True)
    st.caption("Admin-only area. Upload new quarterly PDFs, replace confirmed duplicates, manage saved history, and maintain provider mapping.")

    if not is_admin():
        st.error("Upload and delete controls are admin-only.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    with st.expander("Quarterly service/provider source file", expanded=False):
        st.caption("Upload the current NSW service/provider CSV each quarter/month. This becomes the source of truth for Service Approval Number → legal provider → parent business → sub-brand.")
        current_master = load_service_master()
        if not current_master.empty:
            src = current_master.get("source_file", pd.Series([""])).dropna().astype(str).iloc[0] if "source_file" in current_master.columns and not current_master.empty else ""
            uploaded_at = current_master.get("uploaded_at", pd.Series([""])).dropna().astype(str).iloc[0] if "uploaded_at" in current_master.columns and not current_master.empty else ""
            st.success(f"Current source file loaded: {len(current_master):,} services" + (f" — {src}" if src else "") + (f" — {uploaded_at}" if uploaded_at else ""))
            st.dataframe(current_master[[c for c in ["service_approval_number","provider_approval_number","service_name","provider_legal_name","parent_company","sub_brand","suburb","postcode"] if c in current_master.columns]].head(50), use_container_width=True, hide_index=True, key="service_master_preview_v37")
        service_master_upload = st.file_uploader("Upload service/provider source CSV", type=["csv"], key="service_master_upload_v37")
        if service_master_upload is not None:
            try:
                parsed_master = normalise_service_master_csv(service_master_upload)
                st.info(f"Detected {len(parsed_master):,} services. Preview below. This will replace the current source file when saved.")
                st.dataframe(parsed_master[[c for c in ["service_approval_number","provider_approval_number","service_name","provider_legal_name","parent_company","sub_brand"] if c in parsed_master.columns]].head(100), use_container_width=True, hide_index=True, key="service_master_new_preview_v37")
                if st.button("Save service/provider source file", key="save_service_master_v37", type="primary"):
                    save_service_master(parsed_master, service_master_upload.name)
                    st.success("Service/provider source file saved. Reports will now use Service Approval Number matching where possible.")
                    st.rerun()
            except Exception as e:
                st.error(f"Could not read that CSV: {e}")

    with st.expander("Fallback provider mapping controls", expanded=False):
        st.caption("Fallback mapping is only used when a service is not found in the quarterly service/provider source file.")
        uploaded_map = st.file_uploader("Upload provider_mapping.csv", type=["csv"], key="map_v35")
        map_df = pd.read_csv(uploaded_map) if uploaded_map else rules_to_df()
        edited_map = st.data_editor(map_df, num_rows="dynamic", use_container_width=True, height=280, key="provider_mapping_editor_v35")
        provider_rules = df_to_rules(edited_map)
        st.download_button("Download provider mapping CSV", edited_map.to_csv(index=False), "provider_mapping.csv", "text/csv", key="provider_map_download_v35")
        suggestions = make_auto_mapping_suggestions(hist_actions, provider_rules)
        if not suggestions.empty:
            st.markdown("**Unmapped / auto-discovered provider suggestions**")
            st.caption("Review these and add the valid ones to provider_mapping.csv. This reduces manual clean-up as new centres/providers appear in monthly/quarterly updates.")
            st.dataframe(suggestions, use_container_width=True, hide_index=True, key="mapping_suggestions_v35")
            st.download_button("Download mapping suggestions", suggestions.to_csv(index=False), "provider_mapping_suggestions.csv", "text/csv", key="mapping_suggestions_download_v35")
    provider_rules = df_to_rules(edited_map) if 'edited_map' in locals() else df_to_rules(rules_to_df())

    if st.session_state.get("last_upload_success"):
        su = st.session_state.get("last_upload_success", {})
        st.markdown(f"""
        <div class='ya-success-panel'>
          <div class='ya-success-title'>✅ Upload complete</div>
          <div class='ya-success-grid'>
            <div><strong>Quarter(s)</strong><br>{su.get('quarters','—')}</div>
            <div><strong>Files processed</strong><br>{su.get('files',0)}</div>
            <div><strong>Actions saved</strong><br>{su.get('actions',0)}</div>
            <div><strong>Breach references</strong><br>{su.get('breaches',0)}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class='ya-note' style='margin-top:8px;'>
      Drop any NSW quarterly enforcement PDFs here. You can upload one quarter, a partial quarter, or a full year at once. The app detects quarter/report type and lets you correct them before saving.
    </div>
    """, unsafe_allow_html=True)

    upload_nonce = st.session_state.setdefault("upload_widget_nonce", 0)
    bulk_files = st.file_uploader(
        "Drop all NSW enforcement PDFs here",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"bulk_pdf_upload_v35_{upload_nonce}",
        help="Accepts Service Enforcement, Provider Cancellations, Service Cancellations, and Involuntary Suspensions PDFs. Missing reports are allowed.",
    )
    if bulk_files:
        st.session_state.pop("last_upload_success", None)

    review_df = pd.DataFrame()
    file_text_cache = {}
    if bulk_files:
        with st.spinner("Reading PDF headers and checking saved history…"):
            review_df, file_text_cache = build_upload_review(bulk_files, provider_rules)
        st.markdown("### Upload review")
        st.caption("Fix unidentified files before saving. The review is temporary and disappears after processing.")
        active_review_df = render_upload_review_editor(review_df)
        review_df = active_review_df.copy()

        ready_count = int((active_review_df["Status"] == "Ready").sum()) if not active_review_df.empty else 0
        duplicate_df = active_review_df[active_review_df["Existing rows"].fillna(0).astype(int) > 0] if not active_review_df.empty else pd.DataFrame()
        existing_count = len(duplicate_df)
        blocked_count = len(active_review_df) - ready_count - existing_count
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("Ready to save", ready_count)
        rc2.metric("Already exists", existing_count)
        rc3.metric("Needs check", blocked_count)

        if existing_count:
            duplicate_items = "".join([f"<li>{r['Detected quarter']} — {r['Detected report type']} ({int(r['Existing rows'])} existing rows)</li>" for _, r in duplicate_df.iterrows()])
            st.markdown(f"""
            <div class='ya-duplicate-panel'>
              <h3>Existing data found</h3>
              <p>This quarter/report type has already been uploaded. Upload is blocked until an admin confirms replacement.</p>
              <ul class='ya-duplicate-list'>{duplicate_items}</ul>
            </div>
            """, unsafe_allow_html=True)
            d1, d2, d3 = st.columns([1.2, 1.0, 3])
            with d1:
                if st.button("Replace existing data", key="confirm_replace_duplicates_v35", type="primary"):
                    st.session_state["replace_duplicates_confirmed"] = True
                    st.success("Replacement confirmed. Click Process uploaded PDFs to continue.")
            with d2:
                if st.button("Cancel upload", key="cancel_duplicate_upload_v35"):
                    st.session_state["replace_duplicates_confirmed"] = False
                    st.session_state["upload_removed_files"] = []
                    st.session_state["upload_widget_nonce"] = st.session_state.get("upload_widget_nonce", 0) + 1
                    st.rerun()
            with d3:
                if st.session_state.get("replace_duplicates_confirmed"):
                    st.info("Replacement mode active for this upload only.")
        else:
            st.session_state["replace_duplicates_confirmed"] = False

    process_mode = "Replace existing quarter/report type" if st.session_state.get("replace_duplicates_confirmed") else "Process new files only"

    action_col, history_col = st.columns([1, 1])
    with action_col:
        process_clicked = st.button("Process uploaded PDFs", key="process_bulk_pdfs_v35", type="primary")
    with history_col:
        with st.expander("History manager / delete saved files", expanded=False):
            reports_history = load_reports_history()
            st.caption("Delete saved report files individually or in bulk. Admin password required.")
            if reports_history.empty:
                st.caption("No saved report files yet.")
            else:
                display_cols = [c for c in ["run_id", "quarter", "report_type", "file_name", "uploaded_by", "actions_count", "breaches_count", "processed_at"] if c in reports_history.columns]
                delete_df = reports_history[display_cols].copy()
                delete_df.insert(0, "Delete", False)
                edited_delete_df = st.data_editor(
                    delete_df,
                    use_container_width=True,
                    hide_index=True,
                    key="saved_report_file_delete_editor_v50",
                    column_config={"Delete": st.column_config.CheckboxColumn("Delete", help="Tick files to delete")},
                    disabled=[c for c in delete_df.columns if c != "Delete"],
                )
                selected = edited_delete_df[edited_delete_df["Delete"] == True].drop(columns=["Delete"], errors="ignore")
                st.caption(f"Selected files: {len(selected)}")
                bulk_delete_pw = st.text_input("Admin password to delete selected files", type="password", key="bulk_delete_files_pw_v50")
                bulk_delete_phrase = st.text_input("Type DELETE to confirm selected file deletion", key="bulk_delete_files_phrase_v50")
                if st.button("Delete selected saved files", key="bulk_delete_files_btn_v50", disabled=(selected.empty or bulk_delete_phrase != "DELETE")):
                    if not verify_current_admin_password(bulk_delete_pw):
                        st.error("Admin password incorrect. Nothing deleted.")
                    else:
                        show_soft_loading("Please wait. Deleting selected report files...")
                        count = delete_report_files(selected)
                        st.success(f"Deleted {count} saved report file(s). Refreshing…")
                        st.rerun()

            st.markdown("---")
            st.markdown("### Master reset")
            st.warning("This clears all uploaded reports, extracted data, saved history, uploaded service/provider source data, and audit logs. User accounts remain.")
            reset_pw = st.text_input("Admin password for master reset", type="password", key="master_reset_pw_v50")
            reset_phrase = st.text_input("Type MASTER RESET to confirm", key="master_reset_phrase_v50")
            if st.button("Master reset all uploaded data", key="master_reset_btn_v50", disabled=(reset_phrase != "MASTER RESET")):
                show_soft_loading("Please wait. Performing master reset...")
                ok, msg = master_reset_uploaded_data(reset_pw, reset_phrase)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    if process_clicked:
        if not bulk_files:
            st.error("Upload at least one PDF before processing.")
        else:
            if review_df.empty:
                review_df, file_text_cache = build_upload_review(bulk_files, provider_rules)
            review_df = recalc_upload_review(review_df)
            bad = review_df[review_df["Status"].astype(str).str.startswith("Needs check") | review_df["Status"].astype(str).eq("Duplicate in this upload batch")]
            if not bad.empty:
                st.error("Some uploaded files could not be safely identified or are duplicated in this batch. Remove/fix those files first.")
                st.dataframe(bad, use_container_width=True, hide_index=True, key="bulk_bad_files_v35")
            elif (review_df["Existing rows"].fillna(0).astype(int) > 0).any() and not st.session_state.get("replace_duplicates_confirmed"):
                st.error("Existing data found. Confirm 'Replace existing data' first or cancel the upload.")
            else:
                show_soft_loading("Please wait. Processing uploaded files...")
                run_id = datetime.now().strftime("%Y%m%d%H%M%S")
                all_actions, all_breaches, report_meta = [], [], []
                processed_files = 0
                skipped_files = []
                with st.spinner("Processing bulk upload…"):
                    files_to_process = {str(x) for x in review_df["File"].tolist()}
                    for f in bulk_files:
                        if f.name not in files_to_process:
                            skipped_files.append(f"{f.name} — removed from upload review")
                            continue
                        row = review_df[review_df["File"].eq(f.name)].iloc[0]
                        quarter = str(row["Detected quarter"])
                        rtype = str(row["Detected report type"])
                        existing = int(row["Existing rows"] or 0)
                        if existing and process_mode == "Process new files only":
                            skipped_files.append(f"{f.name} — already uploaded")
                            continue
                        if existing and process_mode == "Replace existing quarter/report type":
                            delete_report_data(quarter, rtype)
                        txt = file_text_cache.get(f.name) or read_pdf_text(f)
                        a, b = parse_pdf(f, quarter, rtype, provider_rules, run_id=run_id, pre_read_text=txt)
                        if a.empty:
                            skipped_files.append(f"{f.name} — no action rows extracted")
                            continue
                        all_actions.append(a)
                        all_breaches.append(b)
                        report_meta.append({
                            "run_id": run_id,
                            "quarter": quarter,
                            "report_type": rtype,
                            "file_name": f.name,
                            "file_signature": file_signature(f),
                            "actions_count": len(a),
                            "breaches_count": len(b),
                            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        })
                        processed_files += 1
                actions = pd.concat(all_actions, ignore_index=True) if all_actions else pd.DataFrame()
                breaches = pd.concat(all_breaches, ignore_index=True) if all_breaches else pd.DataFrame()
                actions, breaches = enrich_with_service_master(actions, breaches)
                meta_df = pd.DataFrame(report_meta)
                if actions.empty:
                    st.warning("No new rows were saved. " + (" Skipped: " + "; ".join(skipped_files[:8]) if skipped_files else ""))
                else:
                    save_to_db(actions, breaches, meta_df)
                    quarters_saved = ", ".join(sorted(actions["quarter"].unique().tolist()))
                    st.session_state["last_upload_success"] = {"quarters": quarters_saved, "files": processed_files, "actions": len(actions), "breaches": len(breaches)}
                    st.session_state["replace_duplicates_confirmed"] = False
                    st.session_state["upload_removed_files"] = []
                    st.session_state["upload_widget_nonce"] = st.session_state.get("upload_widget_nonce", 0) + 1
                    st.success(f"Processed {processed_files} file(s), saved {len(actions)} actions and {len(breaches)} breach references across: {quarters_saved}.")
                    if skipped_files:
                        st.info("Skipped: " + "; ".join(skipped_files[:10]))
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_user_details_page():
    st.markdown("<div class='ya-section-card'>", unsafe_allow_html=True)
    st.markdown("<div class='ya-panel-title'>User Details</div>", unsafe_allow_html=True)
    current = st.session_state.get("current_user", {})
    email = current.get("email", "") if isinstance(current, dict) else ""
    role = current.get("role", "") if isinstance(current, dict) else ""
    st.write(f"**Signed in as:** {email or 'Unknown'}")
    st.write(f"**Role:** {role or ('admin' if is_admin() else 'user')}")
    if is_admin():
        st.markdown("---")
        render_admin_user_manager_panel()
    else:
        st.caption("Your account is read-only. Contact an admin if you require upload or deletion access.")
    st.markdown("</div>", unsafe_allow_html=True)



LAW_GLOSSARY_BASE = {
    "Law 51": ("Conditions on service approval", "The service did not comply with a condition attached to its approval."),
    "Law 56": ("Notice of change to nominated supervisor", "A required nominated supervisor change notice was not managed correctly."),
    "Law 161": ("Nominated supervisor", "The service did not have the required nominated supervisor arrangement in place."),
    "Law 161A": ("Nominated supervisor minimum requirements", "A nominated supervisor did not meet prescribed minimum requirements."),
    "Law 162": ("Responsible person present", "The service operated without the required responsible person present."),
    "Law 162A": ("Child protection training", "A person in day-to-day charge or nominated supervisor did not meet child protection training requirements."),
    "Law 165": ("Inadequate supervision", "Children were not adequately supervised."),
    "Law 166": ("Inappropriate discipline", "A child was subjected to, or exposed to, inappropriate discipline."),
    "Law 166A": ("Inappropriate conduct", "A child was subjected to inappropriate conduct under NSW provisions."),
    "Law 167": ("Protection from harm and hazards", "The service failed to protect children from harm or likely hazards."),
    "Law 168": ("Required programs", "Required educational program obligations were not met."),
    "Law 169": ("Staffing arrangements", "Staffing arrangement obligations were not met."),
    "Law 170": ("Unauthorised persons", "Unauthorised persons were present at the service premises."),
    "Law 172": ("Display prescribed information", "Required information was not displayed as required."),
    "Law 173": ("Notify certain circumstances", "Required notifications to the Regulatory Authority were not made correctly."),
    "Law 174": ("Notify certain information", "Required information was not notified to the Regulatory Authority."),
    "Law 175": ("Keep enrolment/other documents", "Required enrolment or prescribed documents were not kept."),
    "Law 177": ("Compliance notices", "Compliance notice requirements were not met."),
    "Law 182": ("Prohibition notice grounds", "A prohibition-notice related ground was identified."),
    "Law 223B": ("NSW Minister direction", "A NSW Ministerial direction requirement was not met."),
    "Regulation 35": ("Notice of nominated supervisor change", "Required notice about nominated supervisor changes was not managed correctly."),
    "Regulation 55": ("Quality improvement plan", "Quality improvement plan requirements were not met."),
    "Regulation 73": ("Educational program", "Educational program requirements were not met."),
    "Regulation 74": ("Child assessments/evaluations", "Child assessment or evaluation documentation requirements were not met."),
    "Regulation 75": ("Program information available", "Information about the educational program was not kept available."),
    "Regulation 76": ("Program information to parents", "Educational program information was not provided to parents as required."),
    "Regulation 77": ("Health, hygiene and safe food", "Health, hygiene or safe food practice requirements were not met."),
    "Regulation 78": ("Food and beverages", "Food and beverage requirements were not met."),
    "Regulation 79": ("Food service", "Service food provision requirements were not met."),
    "Regulation 80": ("Weekly menu", "Weekly menu requirements were not met."),
    "Regulation 83": ("Alcohol/drugs", "Staff/family day care educator alcohol or drug restrictions were breached."),
    "Regulation 84": ("Child protection law awareness", "Child protection law awareness requirements were not met."),
    "Regulation 84A": ("Sleep and rest", "Sleep and rest requirements were not met."),
    "Regulation 84C": ("Sleep/rest risk assessment", "Required sleep and rest risk assessment was missing or inadequate."),
    "Regulation 84D": ("Bassinets", "Bassinets prohibition requirements were breached."),
    "Regulation 85": ("Incident/injury/trauma/illness policies", "Incident, injury, trauma and illness policy requirements were not met."),
    "Regulation 86": ("Notify parents of incident/injury/trauma/illness", "Parents were not notified as required."),
    "Regulation 87": ("Incident/injury/trauma/illness record", "Required incident/injury/trauma/illness records were incomplete or not kept."),
    "Regulation 89": ("First aid kits", "First aid kit requirements were not met."),
    "Regulation 90": ("Medical conditions policy", "Medical conditions policy requirements were not met."),
    "Regulation 92": ("Medication record", "Medication record requirements were not met."),
    "Regulation 97": ("Emergency and evacuation procedures", "Emergency/evacuation procedure requirements were not met."),
    "Regulation 99": ("Children leaving premises", "Children leaving the premises requirements were not met."),
    "Regulation 100": ("Excursion risk assessment", "Required excursion risk assessment was not conducted correctly."),
    "Regulation 101": ("Conduct of excursion risk assessment", "Excursion risk assessment requirements were not met."),
    "Regulation 102": ("Excursion authorisation", "Excursion authorisation requirements were not met."),
    "Regulation 102B": ("Transport risk assessment", "Transport risk assessment was not conducted before transporting children."),
    "Regulation 102C": ("Transport risk assessment conduct", "Transport risk assessment requirements were not met."),
    "Regulation 102D": ("Transport authorisation", "Authorisation to transport children was not properly obtained."),
    "Regulation 102AAC": ("Safe arrival risk assessment", "Safe arrival policy/procedure risk assessment requirements were not met."),
    "Regulation 103": ("Premises/equipment safe and clean", "Premises, furniture or equipment were not safe, clean or in good repair."),
    "Regulation 104": ("Fencing", "Fencing requirements were not met."),
    "Regulation 105": ("Furniture/materials/equipment", "Furniture, materials or equipment requirements were not met."),
    "Regulation 109": ("Toilet and hygiene facilities", "Toilet or hygiene facility requirements were not met."),
    "Regulation 110": ("Ventilation and natural light", "Ventilation or natural light requirements were not met."),
    "Regulation 113": ("Outdoor space natural environment", "Outdoor natural environment requirements were not met."),
    "Regulation 114": ("Outdoor shade", "Outdoor shade requirements were not met."),
    "Regulation 115": ("Premises designed for supervision", "Premises design did not adequately facilitate supervision."),
    "Regulation 116": ("FDC residence/venue assessment", "Family day care residence/venue assessment requirements were not met."),
    "Regulation 116A": ("Swimming pool/water hazard inspection", "Required inspection of swimming pools/water hazards was not met."),
    "Regulation 116B": ("Inspection report", "Inspection report requirements were not met."),
    "Regulation 116C": ("Swimming pool fencing compliance", "Swimming pool fencing compliance requirements were not met."),
    "Regulation 117A": ("Person in day-to-day charge", "Placement of a person in day-to-day charge requirements were not met."),
    "Regulation 117B": ("Day-to-day charge minimum requirements", "Minimum requirements for a person in day-to-day charge were not met."),
    "Regulation 118": ("Educational leader", "Educational leader requirements were not met."),
    "Regulation 120": ("Under-18 educator supervision", "Educators under 18 were not supervised as required."),
    "Regulation 122": ("Educators working directly with children", "Educator-to-child ratio counting requirements were not met."),
    "Regulation 123": ("Educator-to-child ratios", "Educator-to-child ratio requirements were not met."),
    "Regulation 124": ("FDC educator child numbers", "Family day care child number limits were not met."),
    "Regulation 126": ("Educator qualifications", "General educator qualification requirements were not met."),
    "Regulation 136": ("First aid qualifications", "First aid qualification requirements were not met."),
    "Regulation 143A": ("FDC educator minimum requirements", "Family day care educator minimum requirements were not met."),
    "Regulation 145": ("Staff record", "Staff record requirements were not met."),
    "Regulation 146": ("Nominated supervisor", "Nominated supervisor requirements were not met."),
    "Regulation 147": ("Staff members", "Staff member requirements were not met."),
    "Regulation 149": ("Volunteers/students", "Volunteer/student requirements were not met."),
    "Regulation 150": ("Responsible person", "Responsible person requirements were not met."),
    "Regulation 151": ("Educators working directly records", "Records of educators working directly with children were not kept correctly."),
    "Regulation 155": ("Interactions with children", "Interactions with children requirements were not met."),
    "Regulation 156": ("Relationships in groups", "Relationships in groups requirements were not met."),
    "Regulation 158": ("Children attendance record by provider", "Children's attendance records were not kept by the approved provider as required."),
    "Regulation 159": ("FDC attendance record", "Family day care attendance records were not kept as required."),
    "Regulation 160": ("Child enrolment records", "Child enrolment records were not kept correctly."),
    "Regulation 161": ("Authorisations in enrolment record", "Required authorisations were not kept in enrolment records."),
    "Regulation 162": ("Health information in enrolment record", "Required health information was not kept in enrolment records."),
    "Regulation 163": ("FDC residents/assistants fit and proper", "Family day care residents or assistants were not assessed/managed as fit and proper."),
    "Regulation 165": ("Visitor record", "Visitor records were not kept correctly."),
    "Regulation 167": ("Compliance record", "Service compliance records were not kept correctly."),
    "Regulation 168": ("Policies and procedures", "Required policies and procedures were not in place."),
    "Regulation 169": ("Additional FDC policies/procedures", "Additional family day care policy requirements were not met."),
    "Regulation 170": ("Policies/procedures followed", "Required policies and procedures were not followed."),
    "Regulation 172": ("Notify policy/procedure change", "Required notice of policy/procedure changes was not made."),
    "Regulation 173": ("Prescribed information displayed", "Required prescribed information was not displayed."),
    "Regulation 173A": ("FDC prescribed information displayed", "Family day care prescribed information display requirements were not met."),
    "Regulation 174": ("Time to notify circumstances", "Required notifications were not made within required timeframes."),
    "Regulation 175": ("Prescribed information to RA", "Prescribed information was not notified to the Regulatory Authority."),
    "Regulation 176": ("Time to notify information", "Required information was not notified within required timeframes."),
    "Regulation 177": ("Documents kept by provider", "Prescribed enrolment or other documents were not kept by the provider."),
    "Regulation 178": ("Documents kept by FDC educator", "Prescribed enrolment or other documents were not kept by the family day care educator."),
    "Regulation 185": ("Law/regulations available", "The Law and Regulations were not available as required."),
    "Regulation 272": ("Early childhood teachers", "Early childhood teacher requirements were not met."),
}


def canonical_breach_code(code: str) -> str:
    txt = str(code or "").strip()
    m = re.match(r"^(Law|Regulation)\s+([0-9]{2,3}[A-Z]*(?:AAC|AA|A|B|C|D)?)", txt, flags=re.I)
    if not m:
        return txt
    return f"{m.group(1).title()} {m.group(2).upper()}"


def clean_loaded_frames(actions: pd.DataFrame, breaches: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Clean already-saved history at report time so old dirty uploads do not poison pivots."""
    a = actions.copy() if actions is not None else pd.DataFrame()
    b = breaches.copy() if breaches is not None else pd.DataFrame()
    a, b = enrich_with_service_master(a, b)
    def fix_provider(row):
        provider = str(row.get("provider", ""))
        if provider and not looks_like_action_text(provider) and provider != "Unknown / Needs Mapping":
            return provider
        service = str(row.get("service_name", ""))
        candidate = normalise_provider_stem(service)
        if candidate and not looks_like_action_text(candidate):
            return candidate
        return "Unknown / Needs Mapping"
    if not a.empty:
        a["provider"] = a.apply(fix_provider, axis=1)
    if not b.empty:
        # Breaches often don't have service_name, so build action_id -> clean provider map from actions.
        if not a.empty and "action_id" in a.columns:
            mp = a.drop_duplicates("action_id").set_index("action_id")["provider"].to_dict()
            b["provider"] = b.apply(lambda r: mp.get(r.get("action_id"), clean_provider_name(r.get("provider", ""))), axis=1)
        else:
            b["provider"] = b["provider"].apply(clean_provider_name)
    return a, b


def make_law_glossary(actions: pd.DataFrame, breaches: pd.DataFrame) -> pd.DataFrame:
    """Build an exportable glossary of law/reg references found in uploaded data."""
    if breaches is None or breaches.empty:
        return pd.DataFrame(columns=["breach_code", "reference", "category", "plain_english", "times_breached", "sample_excerpt"])
    b = breaches.copy()
    b["breach_code"] = b["breach_code"].astype(str).map(canonical_breach_code)
    counts = b.groupby(["breach_code", "classification"]).size().reset_index(name="times_breached")
    # raw excerpts by action id
    raw_by_action = {}
    if actions is not None and not actions.empty and "raw_text" in actions.columns:
        raw_by_action = actions.drop_duplicates("action_id").set_index("action_id")["raw_text"].astype(str).to_dict()
    sample = {}
    for _, r in b.iterrows():
        code = r["breach_code"]
        if code in sample:
            continue
        raw = raw_by_action.get(r.get("action_id"), "")
        if raw:
            # Try to capture the first line containing the code number.
            num = re.sub(r"^(Law|Regulation)\s+", "", code)
            lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines()]
            found = next((ln for ln in lines if num in ln and ("Law" in ln or "Regulation" in ln or re.search(r"\b"+re.escape(num)+r"\b", ln))), "")
            sample[code] = found[:220]
    rows = []
    for _, r in counts.sort_values("times_breached", ascending=False).iterrows():
        code = r["breach_code"]
        title, plain = LAW_GLOSSARY_BASE.get(code, ("Needs glossary mapping", "Review the sample excerpt and add a plain-English definition if this code is new."))
        rows.append({
            "breach_code": code,
            "reference": title,
            "category": r["classification"],
            "plain_english": plain,
            "times_breached": int(r["times_breached"]),
            "sample_excerpt": sample.get(code, ""),
            "source": "NSW legislation / Education and Care Services National Law & National Regulations",
            "source_note": "Definitions are plain-English summaries for internal reporting; verify final legal wording against NSW legislation before external use.",
        })
    return pd.DataFrame(rows)

def render_reports_page(hist_actions: pd.DataFrame, hist_breaches: pd.DataFrame, runs: pd.DataFrame):
    hist_actions, hist_breaches = clean_loaded_frames(hist_actions, hist_breaches)
    if hist_actions.empty:
        st.info("No data has been uploaded yet." + (" Go to Upload/Delete Files to start building history." if is_admin() else " Ask an admin to upload reports."))
        return

    all_quarters = sorted_quarter_list(hist_actions)
    quarters_all = list(dict.fromkeys(hist_actions.sort_values("processed_at", ascending=False)["quarter"].astype(str).tolist()))

    selected_quarters = render_quarter_selector(quarters_all)

    show_actions = hist_actions[hist_actions["quarter"].isin(selected_quarters)] if selected_quarters else hist_actions
    show_breaches = hist_breaches[hist_breaches["quarter"].isin(selected_quarters)] if selected_quarters and not hist_breaches.empty else hist_breaches

    if st.session_state.get("provider_detail"):
        provider_detail_view(st.session_state["provider_detail"], hist_actions, hist_breaches, selected_quarters)
        return

    rolling_summary = make_provider_summary(show_actions, show_breaches)
    law_summary = make_law_summary(show_breaches)
    q_summary = quarter_summary(show_actions, show_breaches)
    action_type_summary = show_actions.groupby(["quarter", "action_type"]).size().reset_index(name="Count").sort_values(["quarter", "Count"], ascending=[True, False]) if not show_actions.empty else pd.DataFrame()
    action_category = make_action_category_summary(show_actions)
    breach_category = make_breach_category_summary(show_breaches)
    provider_action_category = make_provider_action_category_summary(show_actions)
    provider_breach_category = make_provider_breach_category_summary(show_breaches)

    st.markdown("## Executive position")
    st.caption("Dynamic based on the selected quarter(s) above.")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Actions", f"{len(show_actions):,}")
    k2.metric("Breach references", f"{len(show_breaches):,}")
    sig_count = int((show_breaches["classification"] == "Significant matter: Law 165/166/167").sum()) if not show_breaches.empty else 0
    k3.metric("L165/166/167", f"{sig_count:,}")
    ya_actions = int((show_actions["provider"] == "Young Academics").sum()) if not show_actions.empty else 0
    k4.metric("YA actions", f"{ya_actions:,}")
    ya_sig = int(((show_breaches["provider"] == "Young Academics") & (show_breaches["classification"] == "Significant matter: Law 165/166/167")).sum()) if not show_breaches.empty else 0
    k5.metric("YA significant", f"{ya_sig:,}")
    with st.expander("What do these executive position numbers mean?", expanded=False):
        render_kpi_notes()

    tab_names = ["Dashboard", "Rolling view", "All time", "Pivot views", "Provider summary", "Law/Reg breakdown", "Law glossary", "Raw extracted rows", "Export"]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        st.caption("Dashboard reflects the selected quarter(s).")
        pie_col1, pie_col2 = st.columns(2)
        with pie_col1:
            render_pie(action_category, "Actions by category", key="pie_actions_selected_v36")
        with pie_col2:
            render_pie(breach_category, "Breach references by category", key="pie_breaches_selected_v36")
        compliance_position = make_compliance_position_table(show_breaches)
        exportable_table(
            "Compliance position by provider",
            compliance_position,
            "compliance_position_v40",
            "compliance_position_by_provider",
            "Board-style breach split for the selected quarter(s): Law 165/166/167 vs all other Law/Reg references.",
        )
        exportable_table("Actions by category", action_category, "action_category_selected_v40", "actions_by_category")
        exportable_table("Breach references by category", breach_category, "breach_category_selected_v40", "breach_references_by_category")
        st.markdown("### Competitor breakdown by category")
        st.caption("Provider/category tables are stacked vertically for readability.")
        exportable_table("Actions by provider/category", provider_action_category, "provider_action_category_v40", "actions_by_provider_category")
        exportable_table("Breaches by provider/category", provider_breach_category, "provider_breach_category_v40", "breaches_by_provider_category")
        gaps = make_mapping_gaps(show_actions)
        if not gaps.empty:
            with st.expander("Mapping gaps / unmatched service IDs", expanded=False):
                st.caption("These rows could not be linked to the uploaded service/provider source file. They are excluded from provider competitor tables until mapped.")
                st.dataframe(gaps, use_container_width=True, hide_index=True, key="mapping_gaps_v38")
                st.download_button("Download mapping gaps CSV", gaps.to_csv(index=False), "mapping_gaps.csv", "text/csv", key="download_mapping_gaps_v38")

    with tabs[1]:
        st.caption("Selected quarters combined. Click one provider row to open a detailed provider summary.")
        try:
            event = st.dataframe(rolling_summary, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="rolling_summary_selectable_v35")
            rows = event.selection.rows if hasattr(event, "selection") else []
            if rows:
                provider = str(rolling_summary.iloc[rows[0]]["provider"])
                st.session_state["provider_detail"] = provider
                st.rerun()
        except TypeError:
            exportable_table("Selected provider ranking", rolling_summary, "rolling_summary_fallback_v40", "selected_provider_ranking")
        exportable_table("Action type summary", action_type_summary, "rolling_action_type_summary_v40", "action_type_summary")

    with tabs[2]:
        st.caption("All uploaded history combined. This ignores quarter selection and shows the true all-time position.")
        all_time_summary = make_provider_summary(hist_actions, hist_breaches)
        exportable_table("All-time provider ranking", all_time_summary, "all_time_provider_ranking_v40", "all_time_provider_ranking")
        exportable_table("All-time action categories", make_action_category_summary(hist_actions), "all_time_action_categories_v40", "all_time_action_categories")
        exportable_table("All-time breach categories", make_breach_category_summary(hist_breaches), "all_time_breach_categories_v40", "all_time_breach_categories")

    with tabs[3]:
        st.caption("Pivot view: providers/issues down the page and quarters running left-to-right in proper financial-year order.")
        pivot_metric = st.selectbox("Pivot metric", ["Actions", "Total breaches", "Significant matters", "Other breaches"], key="pivot_metric_select_v35")
        exportable_table("Provider by quarter pivot", make_provider_pivot(hist_actions, hist_breaches, pivot_metric, all_quarters), "provider_quarter_pivot_v40", "provider_by_quarter_pivot")
        exportable_table("Action type by quarter pivot", make_action_type_pivot(hist_actions, all_quarters), "action_type_quarter_pivot_v40", "action_type_by_quarter_pivot")
        exportable_table("Law/Reg by quarter pivot", make_issue_pivot(hist_breaches, "breach_code", all_quarters), "law_reg_quarter_pivot_v40", "law_reg_by_quarter_pivot")
        exportable_table("Category by quarter pivot", make_issue_pivot(hist_breaches, "classification", all_quarters), "breach_category_quarter_pivot_v40", "category_by_quarter_pivot")

    with tabs[4]:
        provider_list = rolling_summary["provider"].astype(str).tolist() if not rolling_summary.empty else []
        selected_provider = st.selectbox("Choose provider", [""] + provider_list, key="provider_summary_select_v35")
        if selected_provider:
            if st.button("Open provider summary", key="open_provider_summary_button_v35"):
                st.session_state["provider_detail"] = selected_provider
                st.rerun()
            pa = show_actions[show_actions["provider"].eq(selected_provider)]
            pb = show_breaches[show_breaches["provider"].eq(selected_provider)] if not show_breaches.empty else show_breaches
            st.markdown("### Quick provider snapshot")
            st.dataframe(make_provider_summary(pa, pb), use_container_width=True, hide_index=True, key="provider_snapshot_v35")
            render_pie(make_action_category_summary(pa), "Actions by category", key=f"provider_actions_v35_{selected_provider}")
            render_pie(make_breach_category_summary(pb), "Breach references by category", key=f"provider_breaches_v35_{selected_provider}")

    with tabs[5]:
        exportable_table("Law/Reg breakdown", law_summary, "law_summary_v40", "law_reg_breakdown")
        if not show_breaches.empty:
            sig_only = show_breaches[show_breaches["classification"].eq("Significant matter: Law 165/166/167")]
            exportable_table("Serious matters only: Law 165/166/167", make_law_summary(sig_only), "serious_law_summary_v40", "serious_law_summary")

    with tabs[6]:
        glossary_df = make_law_glossary(show_actions, show_breaches)
        st.caption("Plain-English guide to every Law/Reg reference found in the selected data. Export includes the same sheet.")
        exportable_table("Law glossary", glossary_df, "law_glossary_v40", "law_glossary")

    with tabs[7]:
        exportable_table("Extracted enforcement actions", show_actions.drop(columns=["raw_text"], errors="ignore"), "raw_actions_v40", "extracted_enforcement_actions")
        exportable_table("Extracted breach references", show_breaches, "raw_breaches_v40", "extracted_breach_references")

    with tabs[8]:
        all_time_summary = make_provider_summary(hist_actions, hist_breaches)
        provider_pivot_actions = make_provider_pivot(hist_actions, hist_breaches, "Actions", all_quarters)
        provider_pivot_breaches = make_provider_pivot(hist_actions, hist_breaches, "Total breaches", all_quarters)
        law_reg_pivot = make_issue_pivot(hist_breaches, "breach_code", all_quarters)
        action_type_pivot = make_action_type_pivot(hist_actions, all_quarters)
        mapping_suggestions = make_auto_mapping_suggestions(hist_actions, df_to_rules(rules_to_df()))
        sheets = {
            "Selected Provider Ranking": rolling_summary,
            "All Time Provider Ranking": all_time_summary,
            "Provider Pivot Actions": provider_pivot_actions,
            "Provider Pivot Breaches": provider_pivot_breaches,
            "Action Type Pivot": action_type_pivot,
            "Law Reg Pivot": law_reg_pivot,
            "Selected Action Categories": action_category,
            "Selected Breach Categories": breach_category,
            "Provider Action Categories": provider_action_category,
            "Provider Breach Categories": provider_breach_category,
            "Quarter Trend": q_summary,
            "Law Reg Breakdown": law_summary,
            "Law Glossary": make_law_glossary(show_actions, show_breaches),
            "Action Type Summary": action_type_summary,
            "Mapping Suggestions": mapping_suggestions,
            "Extracted Actions": show_actions.drop(columns=["raw_text"], errors="ignore"),
            "Extracted Breaches": show_breaches,
            "Runs History": runs,
            "Uploaded Reports": load_reports_history(),
            "Service Provider Source": load_service_master(),
        }
        xlsx = to_excel_bytes(sheets)
        st.download_button("Download Excel report", xlsx, "YA_Compliance_Benchmark_Report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_excel_report_v35")
        st.download_button("Download full history database", open(DB_PATH, "rb").read(), "compliance_history.sqlite3", "application/octet-stream", key="download_history_db_v35")
        if not mapping_suggestions.empty:
            st.download_button("Download provider mapping suggestions", mapping_suggestions.to_csv(index=False), "provider_mapping_suggestions.csv", "text/csv", key="download_mapping_suggestions_v35")


def main():
    require_login()
    render_header()
    logout_button()

    hist_actions, hist_breaches, runs = load_history()

    if is_admin():
        page_names = ["Reports", "Upload/Delete Files", "User Details"]
    else:
        page_names = ["Reports", "User Details"]
    page_tabs = st.tabs(page_names)

    with page_tabs[0]:
        render_reports_page(hist_actions, hist_breaches, runs)

    if is_admin():
        with page_tabs[1]:
            render_upload_delete_page(hist_actions, hist_breaches, runs)
        with page_tabs[2]:
            render_user_details_page()
    else:
        with page_tabs[1]:
            render_user_details_page()

    st.caption("Internal use only. Review provider mapping before board or Commission reporting, as NSW PDFs often list service names rather than provider groups.")

if __name__ == "__main__":
    main()
