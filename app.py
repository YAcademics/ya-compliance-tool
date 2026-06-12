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

st.set_page_config(page_title=APP_TITLE, page_icon="", layout="wide")

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

[data-baseweb="tag"]::before, [data-baseweb="tag"]::after{display:none!important; content:none!important;}
[data-baseweb="tag"]{padding-left:10px!important; margin-left:0!important;}
[data-baseweb="tag"] > div:first-child{display:none!important;}
[data-testid="stMultiSelect"] [data-baseweb="tag"]{background:#357b84!important; border:1px solid #8edfe4!important;}

.ya-white-panel{background:#ffffff; border-radius:22px; padding:18px; box-shadow:0 10px 24px rgba(0,0,0,.14); border:1px solid #b8dce1; margin:12px 0 18px;}
.ya-white-panel h3,.ya-white-panel h4{color:#00504f!important; margin-top:0;}
.ya-white-panel p,.ya-white-panel li{color:#10242a!important;}

.ya-provider-title{background:#ffffff; border-radius:24px; padding:24px; box-shadow:0 12px 28px rgba(0,0,0,.16); border-left:8px solid #8edfe4; margin-bottom:18px;}
.ya-provider-title h1{color:#00504f!important; margin:0 0 6px 0;}
.ya-provider-title p{color:#10242a!important; margin:0;}

/* Dashboard */
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

[data-baseweb="modal"], [data-baseweb="modal"] > div, [data-baseweb="layer"], div[role="presentation"]{background:transparent!important;opacity:1!important;filter:none!important;}
[data-baseweb="popover"]{z-index:999999!important;opacity:1!important;filter:none!important;}
[data-baseweb="popover"] *, [data-baseweb="menu"] *, [role="listbox"] *{opacity:1!important;filter:none!important;}
[data-baseweb="popover"] ul, [data-baseweb="menu"], [role="listbox"]{background:#ffffff!important;color:#10242a!important;max-height:360px!important;overflow:auto!important;}
[data-baseweb="popover"] li, [role="option"]{color:#10242a!important;background:#ffffff!important;}
[data-baseweb="popover"] li:hover, [role="option"]:hover{background:#eaf6f8!important;color:#00504f!important;}
.stApp, [data-testid="stAppViewContainer"], .main, .block-container{opacity:1!important;filter:none!important;}
@media(max-width:1000px){.ya-review-file{font-size:12px}.ya-review-table{padding:8px}.ya-review-header{display:none}}

[data-testid="stStatusWidget"]{display:none!important;}
[data-testid="stDecoration"]{display:none!important;}
#MainMenu, footer{visibility:hidden;}
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

button[kind="primaryFormSubmit"], button[kind="secondaryFormSubmit"]{border-radius:999px!important;font-weight:900!important;}
button[kind="primaryFormSubmit"]{background:#8edfe4!important;color:#00393c!important;border:0!important;box-shadow:0 5px 0 #1d6d75,0 10px 18px rgba(0,0,0,.18)!important;}
button[kind="secondaryFormSubmit"]{background:#ffffff!important;color:#00504f!important;border:1px solid #b8dce1!important;box-shadow:0 6px 14px rgba(0,0,0,.12)!important;}

[data-baseweb="layer"], [data-baseweb="layer"] > div{background:transparent!important;opacity:1!important;filter:none!important;}
[data-baseweb="popover"]{background:transparent!important;opacity:1!important;filter:none!important;z-index:2147483647!important;}
[data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"]{background:#ffffff!important;border:1px solid #c9dfe3!important;box-shadow:0 18px 34px rgba(0,0,0,.20)!important;border-radius:14px!important;overflow:auto!important;max-height:340px!important;}
[data-baseweb="popover"] [role="option"], [data-baseweb="menu"] li{background:#ffffff!important;color:#10242a!important;}
[data-baseweb="popover"] [role="option"]:hover, [data-baseweb="menu"] li:hover{background:#eaf6f8!important;color:#00504f!important;}

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


def init_db():
    """Initializes schema and runs safe backward-compatible dynamic column migrations."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Base users lookup table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        email TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT,
        created_by TEXT
    )
    """)

    # Compliance history tracks details safely
    cur.execute("""
    CREATE TABLE IF NOT EXISTS compliance_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        filename TEXT,
        file_hash TEXT,
        provider TEXT,
        service_id TEXT,
        service_name TEXT,
        date TEXT,
        law TEXT,
        regulation TEXT,
        nature_of_breach TEXT,
        action_required TEXT,
        status TEXT,
        quarter TEXT,
        calendar_year INTEGER
    )
    """)

    # Audit engine logging
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

    # Normalization context rules
    cur.execute("""
    CREATE TABLE IF NOT EXISTS provider_mapping (
        raw_string TEXT PRIMARY KEY,
        clean_provider TEXT
    )
    """)

    con.commit()

    # Core Auto-Migration for dynamically introduced Quarter Chips dimensions
    try:
        cur.execute("PRAGMA table_info(compliance_history)")
        columns = [col[1] for col in cur.fetchall()]
        if "quarter" not in columns:
            cur.execute("ALTER TABLE compliance_history ADD COLUMN quarter TEXT;")
        if "calendar_year" not in columns:
            cur.execute("ALTER TABLE compliance_history ADD COLUMN calendar_year INTEGER;")
        con.commit()
    except Exception:
        pass

    con.close()


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
    con.commit()
    con.close()


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
        con.commit()
        con.close()
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


def load_history() -> Tuple[pd.DataFrame, pd.DataFrame, List[dict]]:
    """Loads records safely from storage mapping time periods correctly."""
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM compliance_history", con)
    con.close()

    if df.empty:
        empty_df = pd.DataFrame(columns=[
            'id', 'run_id', 'filename', 'file_hash', 'provider', 'service_id', 
            'service_name', 'date', 'law', 'regulation', 'nature_of_breach', 
            'action_required', 'status', 'quarter', 'calendar_year'
        ])
        return empty_df, empty_df, []

    # Dynamic fallback recalculation loop if database records are unpopulated
    if 'quarter' not in df.columns or df['quarter'].isnull().all():
        df['quarter'] = "Q1"
    if 'calendar_year' not in df.columns or df['calendar_year'].isnull().all():
        df['calendar_year'] = 2026

    # Convert numeric assignments securely
    df['calendar_year'] = pd.to_numeric(df['calendar_year'], errors='coerce').fillna(2026).astype(int)

    runs_grouped = df.groupby('run_id').agg({
        'filename': 'first',
        'date': 'max'
    }).reset_index()
    runs = [{"run_id": r['run_id'], "filename": r['filename'], "processed_at": r['date']} for _, r in runs_grouped.iterrows()]

    return df, df, runs


def save_to_db(run_id: str, filename: str, file_hash: str, df: pd.DataFrame):
    """Saves records safely, ignoring transient front-end filter tracking artifacts if necessary."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for _, row in df.iterrows():
        # Extrapolate periods securely or extract defaults
        q_val = str(row.get('quarter', 'Q1')) if 'quarter' in row else 'Q1'
        y_val = int(row.get('calendar_year', 2026)) if 'calendar_year' in row else 2026

        cur.execute("""
            INSERT INTO compliance_history (
                run_id, filename, file_hash, provider, service_id, service_name, 
                date, law, regulation, nature_of_breach, action_required, status, 
                quarter, calendar_year
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, filename, file_hash,
            str(row.get('provider', 'Unknown')),
            str(row.get('service_id', '')),
            str(row.get('service_name', '')),
            str(row.get('date', now_str)),
            str(row.get('law', '')),
            str(row.get('regulation', '')),
            str(row.get('nature_of_breach', '')),
            str(row.get('action_required', '')),
            str(row.get('status', 'Open')),
            q_val, y_val
        ))
    con.commit()
    con.close()


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
    </div>
    """, unsafe_allow_html=True)

    with st.form("ya_login_form"):
        st.subheader("Sign In")
        email = st.text_input("Corporate Email")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Authenticate")

        if submit:
            user, error = authenticate_user(email, password)
            if error:
                st.error(error)
            else:
                st.session_state["current_user"] = user
                log_audit("login", "Successful web interface authentication")
                st.rerun()


def require_login():
    if "current_user" not in st.session_state:
        render_login_screen()
        st.stop()


def logout_button():
    if st.sidebar.button("Log Out"):
        log_audit("logout", "User dropped session state context")
        st.session_state.pop("current_user", None)
        st.rerun()


def render_header():
    st.markdown(f"""
    <div class='ya-shell'>
      <div class='ya-header'>
        <div class='ya-brand'>
          <img class='ya-logo' src='{LOGO_URL}' />
          <div class='ya-title'>
            <h1>{APP_TITLE}</h1>
            <p>Young Academics Market Monitoring & Internal Compliance Analysis Intelligence</p>
          </div>
        </div>
        <div class='ya-version'>{APP_VERSION}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def parse_compliance_text(text: str) -> List[dict]:
    """Scrapes raw document elements matching operational context laws."""
    records = []
    current_record = {}

    lines = text.split("\n")
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        # Check for new entry marker patterns
        id_match = ID_RE.search(cleaned)
        if id_match:
            if current_record and (current_record.get('law') or current_record.get('regulation')):
                records.append(current_record)
            current_record = {
                'service_id': id_match.group(1),
                'provider': 'Unknown',
                'service_name': '',
                'date': datetime.now().strftime("%Y-%m-%d"),
                'law': '',
                'regulation': '',
                'nature_of_breach': '',
                'action_required': '',
                'status': 'Open',
                'quarter': 'Q1',
                'calendar_year': 2026
            }

        if not current_record:
            continue

        # Extract context attributes cleanly
        date_match = DATE_RE.search(cleaned)
        if date_match and 'date' not in current_record:
            current_record['date'] = date_match.group(1)

        law_match = LAW_RE.search(cleaned)
        if law_match:
            current_record['law'] = law_match.group(1)

        reg_match = REG_RE.search(cleaned)
        if reg_match:
            current_record['regulation'] = reg_match.group(1)

    if current_record and (current_record.get('law') or current_record.get('regulation')):
        records.append(current_record)

    return records


def render_reports_page(hist_actions, hist_breaches, runs):
    st.markdown("<div class='ya-section-card'><h2 class='ya-panel-title'>Compliance Intelligence Matrix Dashboard</h2></div>", unsafe_allow_html=True)

    if hist_actions.empty:
        st.info("No enforcement context currently saved inside the persistence tracking engine database.")
        return

    # Quarter Selection Chips Core Component
    st.markdown("### Time Period Filtering")
    available_years = sorted(list(hist_actions['calendar_year'].unique()))
    selected_year = st.selectbox("Select Year Focus", available_years if available_years else [2026])

    available_quarters = sorted(list(hist_actions['quarter'].unique()))
    selected_quarters = st.multiselect("Select Active Quarters", available_quarters, default=available_quarters)

    # Filtering rows matching user context metrics selections
    filtered_df = hist_actions[
        (hist_actions['calendar_year'] == selected_year) & 
        (hist_actions['quarter'].isin(selected_quarters))
    ]

    # Metrics Display Cards
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Extracted Incidents", len(filtered_df))
    m2.metric("Significant Breaches (Laws 165-167)", len(filtered_df[filtered_df['law'].isin(SIGNIFICANT_LAWS)]))
    m3.metric("Unique Entities Profiled", filtered_df['provider'].nunique())

    st.markdown("#### Complete Dataset Context View")
    st.dataframe(filtered_df)


def render_upload_delete_page(hist_actions, hist_breaches, runs):
    st.markdown("<div class='ya-section-card'><h2 class='ya-panel-title'>Document Ingestion & System Storage Flush</h2></div>", unsafe_allow_html=True)

    uploaded_file = st.file_uploader("Upload Raw Provider PDF Report", type=["pdf", "txt"])
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Check for duplication records before parsing logic loop running
        con = sqlite3.connect(DB_PATH)
        dup = con.execute("SELECT filename FROM compliance_history WHERE file_hash=?", (file_hash,)).fetchone()
        con.close()

        if dup:
            st.warning(f"File duplicate detected. This exact payload has already been ingested under filename: {dup[0]}")
        else:
            if st.button("Execute Compliance Ingestion Model"):
                text_content = ""
                if uploaded_file.name.endswith(".pdf") and pdfplumber:
                    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                        text_content = "\n".join([page.extract_text() or "" for page in pdf.pages])
                else:
                    text_content = file_bytes.decode("utf-8", errors="ignore")

                parsed_records = parse_compliance_text(text_content)
                if parsed_records:
                    run_id = f"RUN_{int(time.time())}"
                    parsed_df = pd.DataFrame(parsed_records)
                    save_to_db(run_id, uploaded_file.name, file_hash, parsed_df)
                    st.success(f"Successfully processed and committed {len(parsed_records)} rows into storage tables.")
                    st.rerun()
                else:
                    st.error("No legal infraction context patterns matched within your source document structure.")


def render_user_details_page():
    st.markdown("<div class='ya-section-card'><h2 class='ya-panel-title'>User Access State Information</h2></div>", unsafe_allow_html=True)
    st.write(f"**Authenticated Email Reference:** {current_user_email()}")
    st.write(f"**Assigned System Context Permission Role Tier:** {current_user_role().upper()}")


def main():
    init_db()
    ensure_default_users()
    require_login()
    render_header()
    logout_button()

    hist_actions, hist_breaches, runs = load_history()

    page_names = ["Reports", "Upload/Delete Files", "User Details"] if is_admin() else ["Reports", "User Details"]
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


if __name__ == "__main__":
    main()
