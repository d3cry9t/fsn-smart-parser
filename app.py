def parse_scenarios(raw_text, mode, selected_keys):
    """Translate free-text pricing notes into upload rows."""
    if not selected_keys:
        return pd.DataFrame(columns=_OUT_COLS)

    blocks = re.split(r"([A-Z0-9]{16})", raw_text)
    if len(blocks) < 2:
        return pd.DataFrame(columns=_OUT_COLS)

    rows = []
    for i in range(1, len(blocks), 2):
        fsn = blocks[i].strip()
        context = blocks[i + 1].upper() if i + 1 < len(blocks) else ""

        # Check if "ASP" is explicitly mentioned in the text following the FSN
        has_asp_keyword = "ASP" in context

        # "2,279" is one number (2279); drop commas only between two digits.
        context = re.sub(r"(?<=\d),(?=\d)", "", context)

        is_event = (mode == "Event") or any(w in context for w in ("SALE", "EVENT", "LIVE"))

        lt_abs = None
        lt_rel = None
        lt_span = None

        m_abs = re.search(r"\bLT\s*(\d+(?:\.\d+)?)\b", context)
        if m_abs:
            lt_abs = float(m_abs.group(1))
            lt_span = m_abs.group(0)
        else:
            m_signed = re.search(r"(?:LT\s*)?([+\-]\s*\d+(?:\.\d+)?)", context)
            m_plus = re.search(r"\bPLUS\s*(\d+(?:\.\d+)?)", context)
            m_minus = re.search(r"\bMINUS\s*(\d+(?:\.\d+)?)", context)
            if m_signed:
                lt_rel = float(re.sub(r"\s+", "", m_signed.group(1)))
                lt_span = m_signed.group(0)
            elif m_plus:
                lt_rel = float(m_plus.group(1))
                lt_span = m_plus.group(0)
            elif m_minus:
                lt_rel = -float(m_minus.group(1))
                lt_span = m_minus.group(0)

        base_text = context.replace(lt_span, " ", 1) if lt_span else context
        base_perc = None
        base_asp = None
        for tok in re.findall(_NUM, base_text):
            num = float(tok)
            # If "ASP" is in the text, treat the number as an absolute value regardless of size
            if has_asp_keyword:
                base_asp = num
            elif 0 <= num <= 100:          # 0 is a valid percentage
                base_perc = num
            elif num > 100 or num < 0:
                base_asp = num

        if lt_abs is not None:
            # Force ASP type if keyword is present
            lt_kind = "asp" if has_asp_keyword else _value_kind(lt_abs)
        elif lt_rel is not None:
            if base_perc is not None and base_asp is None:
                lt_kind = "perc"
            elif base_asp is not None and base_perc is None:
                lt_kind = "asp"
            else:
                # Force ASP if keyword is present, otherwise fallback to magnitude logic
                lt_kind = "asp" if has_asp_keyword else ("perc" if abs(lt_rel) < 100 else "asp")
        else:
            lt_kind = None

        for key in selected_keys:
            is_perc = key in PERC_KEYS
            is_asp = key in ASP_KEYS
            is_lt = key.startswith("LT")
            kind = "perc" if is_perc else ("asp" if is_asp else None)
            base = base_perc if is_perc else (base_asp if is_asp else None)

            if mode != "Manual":
                if is_event and key in ("UT_disc_percent_cat", "custom_14"):
                    continue
                if not is_event and key in ("mrp_disc_percent", "custom_15"):
                    continue

            val = None
            if is_lt:
                if lt_abs is not None and lt_kind == kind:
                    val = lt_abs
                elif lt_rel is not None and lt_kind == kind and base is not None:
                    val = base + lt_rel
                elif base is not None:
                    val = base
            else:
                if base is not None:
                    val = base

            if val is not None:
                rows.append({"fsn": fsn, "key": key, "value": val, "expiry": ""})

    return pd.DataFrame(rows, columns=_OUT_COLS)
