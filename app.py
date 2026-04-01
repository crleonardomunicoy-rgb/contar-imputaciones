import streamlit as st
import pandas as pd
import pdfplumber
import re
import tempfile
import os

st.set_page_config(page_title="Contar - Imputación de Compras", layout="wide")

st.title("🧠 Contar - Imputación desde Compras Unificadas")

st.info("⚠️ Subir archivo de compras generado por el sistema Contar")

# ---------------------------
# FUNCIONES
# ---------------------------

def limpiar_cuit(valor):
    if pd.isna(valor):
        return ""
    return re.sub(r"\D", "", str(valor))

# ---------------------------
# LEER COMPRAS DESDE EXCEL
# ---------------------------

def cargar_compras(file):
    df = pd.read_excel(file)

    columnas_necesarias = [
        "Nro. Doc. Vendedor",
        "Denominación del Vendedor",
        "Importe Total"
    ]

    faltantes = [c for c in columnas_necesarias if c not in df.columns]

    if faltantes:
        st.error(f"❌ El archivo no tiene columnas necesarias: {faltantes}")
        st.stop()

    df["CUIT"] = df["Nro. Doc. Vendedor"].apply(limpiar_cuit)

    return df

# ---------------------------
# GENERAR PADRÓN
# ---------------------------

def generar_padron(df):
    padron = (
        df.groupby("CUIT")
        .agg({
            "Denominación del Vendedor": "last",
            "Importe Total": "sum",
            "CUIT": "count"
        })
        .rename(columns={
            "Denominación del Vendedor": "Proveedor",
            "Importe Total": "Importe Total",
            "CUIT": "Cantidad Comprobantes"
        })
        .reset_index()
    )

    return padron

# ---------------------------
# PLAN DE CUENTAS PDF
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
# SUGERENCIAS POR REGLAS
# ---------------------------

def sugerir(proveedor, plan):
    nombre = proveedor.upper()

    sugerencias = []

    for _, row in plan.iterrows():
        codigo = row["Codigo"]
        cuenta = row["Cuenta"].upper()

        score = 0

        if "YPF" in nombre or "SHELL" in nombre:
            if "COMBUST" in cuenta:
                score += 10

        if "TRANSP" in nombre:
            if "FLETE" in cuenta or "TRANSP" in cuenta:
                score += 10

        if "ESTUDIO" in nombre:
            if "HONOR" in cuenta:
                score += 10

        if score > 0:
            sugerencias.append((codigo, cuenta, score))

    sugerencias = sorted(sugerencias, key=lambda x: x[2], reverse=True)

    return sugerencias[:3]

# ---------------------------
# INTERFAZ
# ---------------------------

st.subheader("1️⃣ Subir archivo de compras")
archivo_compras = st.file_uploader("Subir Excel de compras", type=["xlsx"])

st.subheader("2️⃣ Subir plan de cuentas")
archivo_plan = st.file_uploader("Subir PDF", type=["pdf"])

st.subheader("3️⃣ Subir memoria (opcional)")
archivo_memoria = st.file_uploader("Subir memoria", type=["xlsx"])

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
