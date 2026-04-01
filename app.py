import streamlit as st
import pandas as pd
import pdfplumber
import re
import tempfile
import os

st.set_page_config(page_title="Contar - Imputación desde Compras", layout="wide")

st.title("🧠 Contar - Imputación desde Compras Unificadas")

st.info("⚠️ Subir archivo de compras generado por AFIP / sistema Contar")

# ---------------------------
# FUNCIONES
# ---------------------------

def limpiar_cuit(valor):
    if pd.isna(valor):
        return ""
    return re.sub(r"\D", "", str(valor))

def normalizar_columnas(df):
    df.columns = df.columns.str.strip()
    df.columns = df.columns.str.replace("\n", " ")
    df.columns = df.columns.str.replace("  ", " ")
    return df

# ---------------------------
# CARGA DE COMPRAS (ROBUSTA)
# ---------------------------

def cargar_compras(file):
    df = pd.read_excel(file)
    df = normalizar_columnas(df)

    columnas = df.columns.tolist()

    col_cuit = "Nro. Doc. Vendedor" if "Nro. Doc. Vendedor" in columnas else None
    col_proveedor = "Denominación Vendedor" if "Denominación Vendedor" in columnas else None
    col_importe = "Importe Total" if "Importe Total" in columnas else None

    # fallback inteligente
    if not col_proveedor:
        for col in columnas:
            if "denominacion" in col.lower() or "nombre" in col.lower():
                col_proveedor = col
                break

    if not col_cuit:
        for col in columnas:
            if "doc" in col.lower() and "vendedor" in col.lower():
                col_cuit = col
                break

    if not col_importe:
        for col in columnas:
            if "importe total" in col.lower():
                col_importe = col
                break

    if not col_cuit or not col_proveedor or not col_importe:
        st.error("❌ No se pudieron identificar las columnas necesarias")
        st.write("Columnas detectadas:", columnas)
        st.stop()

    df["CUIT"] = df[col_cuit].apply(limpiar_cuit)
    df["Proveedor"] = df[col_proveedor]
    df["Importe Total"] = df[col_importe]

    st.success("✅ Columnas identificadas correctamente")

    return df

# ---------------------------
# GENERAR PADRÓN
# ---------------------------

def generar_padron(df):
    padron = (
        df.groupby("CUIT")
        .agg({
            "Proveedor": "last",
            "Importe Total": "sum",
            "CUIT": "count"
        })
        .rename(columns={
            "Proveedor": "Proveedor",
            "Importe Total": "Importe Total",
            "CUIT": "Cantidad Comprobantes"
        })
        .reset_index()
    )

    return padron

# ---------------------------
# PLAN DE CUENTAS
# ---------------------------

def leer_plan_cuentas_pdf(file):
    cuentas = []

    with pdfplumber.open(file) as pdf:
        texto_total = ""

        for page in pdf.pages:
            texto = page.extract_text()
            if texto:
                texto_total += texto + "\n"

    lineas = texto_total.split("\n")

    for linea in lineas:
        linea = linea.strip()

        if not linea:
            continue

        match = re.match(r"^([\d\.\-]+)\s+(.*)$", linea)

        if match:
            cuentas.append({
                "Codigo": match.group(1),
                "Cuenta": match.group(2)
            })

    return pd.DataFrame(cuentas).drop_duplicates()

# ---------------------------
# MEMORIA
# ---------------------------

def cargar_memoria(file):
    df = pd.read_excel(file)

    columnas_esperadas = [
        "CUIT",
        "Proveedor",
        "Codigo_Cuenta_Final",
        "Cuenta_Final"
    ]

    faltantes = [c for c in columnas_esperadas if c not in df.columns]

    if faltantes:
        st.error(f"❌ Memoria incorrecta. Faltan columnas: {faltantes}")
        st.stop()

    df["CUIT"] = df["CUIT"].apply(limpiar_cuit)

    return df

# ---------------------------
# BUSCAR MEMORIA
# ---------------------------

def buscar_memoria(cuit, memoria):
    if memoria is None:
        return None

    match = memoria[memoria["CUIT"] == cuit]

    if match.empty:
        return None

    fila = match.iloc[-1]

    return fila["Codigo_Cuenta_Final"], fila["Cuenta_Final"]

# ---------------------------
# SUGERENCIAS
# ---------------------------

def sugerir(proveedor, plan):
    nombre = proveedor.upper()

    sugerencias = []

    for _, row in plan.iterrows():
        codigo = row["Codigo"]
        cuenta = row["Cuenta"]
        cuenta_upper = cuenta.upper()

        score = 0

        if "YPF" in nombre or "SHELL" in nombre:
            if "COMBUST" in cuenta_upper:
                score += 10

        if "TRANSP" in nombre or "FLETE" in nombre:
            if "FLETE" in cuenta_upper:
                score += 10

        if "ESTUDIO" in nombre or "CONSULT" in nombre:
            if "HONOR" in cuenta_upper:
                score += 10

        if "FERRE" in nombre or "CORRALON" in nombre:
            if "MATERIA" in cuenta_upper or "INSUMO" in cuenta_upper:
                score += 8

        if score > 0:
            sugerencias.append((codigo, cuenta, score))

    sugerencias = sorted(sugerencias, key=lambda x: x[2], reverse=True)

    return sugerencias[:3]

# ---------------------------
# INTERFAZ
# ---------------------------

st.subheader("1️⃣ Subir archivo de compras")
archivo_compras = st.file_uploader("Excel compras", type=["xlsx"])

st.subheader("2️⃣ Subir plan de cuentas")
archivo_plan = st.file_uploader("PDF plan de cuentas", type=["pdf"])

st.subheader("3️⃣ Subir memoria (opcional)")
archivo_memoria = st.file_uploader("Excel memoria", type=["xlsx"])

# ---------------------------
# PROCESO
# ---------------------------

if st.button("🚀 Procesar"):

    if archivo_compras is None or archivo_plan is None:
        st.error("❌ Faltan archivos obligatorios")
        st.stop()

    compras = cargar_compras(archivo_compras)
    padron = generar_padron(compras)
    plan = leer_plan_cuentas_pdf(archivo_plan)

    memoria = None
    if archivo_memoria:
        memoria = cargar_memoria(archivo_memoria)

    resultados = []

    for _, row in padron.iterrows():

        cuit = row["CUIT"]
        proveedor = row["Proveedor"]

        cod_mem = ""
        cuenta_mem = ""
        origen = "REGLAS"
        conflicto = "NO"

        memoria_match = buscar_memoria(cuit, memoria)
        sugerencias = sugerir(proveedor, plan)

        cod1 = cod2 = cod3 = ""
        cta1 = cta2 = cta3 = ""

        if len(sugerencias) > 0:
            cod1, cta1, _ = sugerencias[0]
        if len(sugerencias) > 1:
            cod2, cta2, _ = sugerencias[1]
        if len(sugerencias) > 2:
            cod3, cta3, _ = sugerencias[2]

        if memoria_match:
            cod_mem, cuenta_mem = memoria_match
            origen = "MEMORIA"

            if cod1 != "" and cod_mem != cod1:
                conflicto = "SI"

        resultados.append({
            "CUIT": cuit,
            "Proveedor": proveedor,
            "Codigo_Memoria": cod_mem,
            "Cuenta_Memoria": cuenta_mem,
            "Codigo_Sugerida_1": cod1,
            "Cuenta_Sugerida_1": cta1,
            "Codigo_Sugerida_2": cod2,
            "Cuenta_Sugerida_2": cta2,
            "Codigo_Sugerida_3": cod3,
            "Cuenta_Sugerida_3": cta3,
            "Origen": origen,
            "Conflicto": conflicto,
            "Codigo_Cuenta_Final": "",
            "Cuenta_Final": "",
            "Validado": "NO"
        })

    df = pd.DataFrame(resultados)
    conflictos = df[df["Conflicto"] == "SI"]

    output_path = os.path.join(tempfile.gettempdir(), "imputacion.xlsx")

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Padron_Imputado", index=False)
        conflictos.to_excel(writer, sheet_name="Conflictos", index=False)

    with open(output_path, "rb") as f:
        st.download_button("📥 Descargar Resultado", f, "imputacion.xlsx")

    st.success("✅ Proceso terminado")
