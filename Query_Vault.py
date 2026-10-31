import re

import streamlit as st

import db

st.set_page_config(page_title="Query Vault", page_icon="🗄️", layout="wide")
st.title("Query Vault")
st.caption("Save validated queries once. Reuse with {{placeholders}} filled in.")

tab_find, tab_add, tab_io = st.tabs(["Find & use", "Add / edit", "Backup"])


def placeholders(sql):
    return list(dict.fromkeys(re.findall(r"\{\{\s*(\w+)\s*\}\}", sql or "")))


with tab_find:
    c1, c2, c3 = st.columns([3, 1, 1])
    q = c1.text_input("Search", placeholder="title, purpose, tags, tables, SQL text")
    eng = c2.selectbox("Engine", ["All"] + db.ENGINES)
    sort = c3.selectbox("Sort", ["Recently used", "Most used", "Newest"])
    df = db.read("SELECT * FROM queries")
    if eng != "All":
        df = df[df.engine == eng]
    if q:
        blob = df[["title", "purpose", "tags", "tables_used", "sql"]].fillna("").agg(" ".join, axis=1).str.lower()
        df = df[blob.str.contains(q.lower(), regex=False)]
    df = df.sort_values({"Recently used": "updated", "Most used": "use_count", "Newest": "created"}[sort],
                        ascending=False)
    st.caption(f"{len(df)} quer{'y' if len(df) == 1 else 'ies'}")

    for _, r in df.iterrows():
        with st.expander(f"{r.title}  ·  {r.engine}  ·  used {r.use_count}x"):
            st.write(r.purpose or "")
            st.caption(f"Tables: {r.tables_used or '-'}  |  Tags: {r.tags or '-'}  |  "
                       f"Verified against: {r.verified_against or '-'}")
            if r.gotchas:
                st.warning(r.gotchas)
            sql = r.sql
            ph = placeholders(sql)
            if ph:
                cols = st.columns(min(len(ph), 4))
                for i, p in enumerate(ph):
                    v = cols[i % 4].text_input(p, key=f"ph_{r.id}_{p}")
                    if v:
                        sql = re.sub(r"\{\{\s*" + p + r"\s*\}\}", v, sql)
            st.code(sql, language="sql")  # built-in copy button
            b1, b2 = st.columns([1, 6])
            if b1.button("Mark used", key=f"use_{r.id}"):
                db.run("UPDATE queries SET use_count=use_count+1, updated=CURRENT_TIMESTAMP WHERE id=?", (int(r.id),))
                st.rerun()
            if b2.button("Delete", key=f"del_{r.id}"):
                db.run("DELETE FROM queries WHERE id=?", (int(r.id),))
                st.rerun()

with tab_add:
    all_q = db.read("SELECT id, title FROM queries ORDER BY title")
    pick = st.selectbox("Edit existing (or leave blank for new)", [None] + all_q.id.tolist(),
                        format_func=lambda i: "— new —" if i is None else all_q.set_index("id").title[i])
    cur = db.read("SELECT * FROM queries WHERE id=?", (pick,)).iloc[0] if pick else None
    g = (lambda k: cur[k] if cur is not None and cur[k] else "")
    with st.form("qform", clear_on_submit=pick is None):
        title = st.text_input("Title *", g("title"))
        a, b = st.columns(2)
        engine = a.selectbox("Engine", db.ENGINES, index=db.ENGINES.index(g("engine") or "BigQuery"))
        tags = b.text_input("Tags (comma separated)", g("tags"))
        purpose = st.text_area("Purpose", g("purpose"), height=70)
        tables = st.text_input("Tables used", g("tables_used"))
        sql = st.text_area("SQL * (use {{param}} for variables, e.g. {{start_date}})", g("sql"), height=250)
        gotchas = st.text_area("Gotchas (partition filters, duplicates, known traps)", g("gotchas"), height=70)
        ver = st.text_input("Verified against (e.g. 'matched Excel total 12,340 rows on 31 Oct')", g("verified_against"))
        if st.form_submit_button("Save", type="primary"):
            if not title.strip() or not sql.strip():
                st.error("Title and SQL are required.")
            elif pick:
                db.run("UPDATE queries SET title=?,engine=?,purpose=?,tables_used=?,tags=?,sql=?,gotchas=?,"
                       "verified_against=?,updated=CURRENT_TIMESTAMP WHERE id=?",
                       (title, engine, purpose, tables, tags, sql, gotchas, ver, int(pick)))
                st.success("Updated.")
            else:
                db.run("INSERT INTO queries(title,engine,purpose,tables_used,tags,sql,gotchas,verified_against)"
                       " VALUES(?,?,?,?,?,?,?,?)", (title, engine, purpose, tables, tags, sql, gotchas, ver))
                st.success("Saved.")

with tab_io:
    import pandas as pd
    st.download_button("Export all queries (CSV)", db.read("SELECT * FROM queries").to_csv(index=False).encode(),
                       "query_vault_backup.csv", "text/csv")
    up = st.file_uploader("Import CSV (from an earlier export)", type="csv")
    if up and st.button("Import"):
        imp = pd.read_csv(up).fillna("")
        for _, r in imp.iterrows():
            db.run("INSERT INTO queries(title,engine,purpose,tables_used,tags,sql,gotchas,verified_against)"
                   " VALUES(?,?,?,?,?,?,?,?)",
                   (r.title, r.engine, r.purpose, r.tables_used, r.tags, r.sql, r.gotchas, r.verified_against))
        st.success(f"Imported {len(imp)}.")
