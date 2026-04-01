import streamlit as st
import pandas as pd
import tempfile
import os

st.set_page_config(page_title="Contar - Imputación de Proveedores", layout="wide")

st.title("🧠 Contar - Imputación de Proveedores con Memoria por Cliente")

st.markdown("""
Subí:
1. El padrón de proveedores generado por la app anterior  
2. El plan de cuentas del cliente  
3. La memoria histórica del cliente (opcional pero recomendada)  
4. La actividad de la empresa  

La herramienta prioriza la memoria histórica del cliente y deja una instancia manual de validación.
""")

# =========================
# INPUTS
# =========================
actividad_empresa = st.text_area(
    "Actividad de la empresa",
    placeholder="Ej: Instalación de piscinas y venta de insumos"
)

archivo_padron = st.file_uploader(
    "Subir padrón de proveedores (Excel generado por la app 1)",
    type=["xlsx"]
)

archivo_plan = st.file_uploader(
    "Subir plan de cuentas (Excel)",
    type=["xlsx"]
)

archivo_memoria = st.file_uploader(
    "Subir memoria histórica del cliente (opcional)",
    type=["xlsx"]
)

# =========================
# FUNCIONES AUXILIARES
# =========================
def limpiar_cuit(valor):
    if pd.isna(valor):
        return ""
    return "".join(ch for ch in str(valor) if ch.isdigit())

def detectar_columna(df, posibles):
    for col in df.columns:
        nombre = str(col).strip().lower()
        for p in posibles:
            if p in nombre:
                return col
    return None

def normalizar_columnas(df):
    df.columns = [str(c).strip() for c in df.columns]
    return df

def sugerir_por_reglas(nombre_proveedor, actividad_empresa, plan_df):
    """
    Devuelve hasta 3 sugerencias:
    [(codigo, cuenta, score), ...]
    """
    nombre = str(nombre_proveedor).upper()
    actividad = str(actividad_empresa).upper()

    sugerencias = []

    for _, row in plan_df.iterrows():
        codigo = str(row["Código"]).strip()
        cuenta = str(row["Cuenta"]).strip()
        cuenta_upper = cuenta.upper()
        score = 0

        # Combustibles
        if any(x in nombre for x in ["YPF", "SHELL", "AXION", "PUMA", "COMBUST"]):
            if any(x in cuenta_upper for x in ["COMBUST", "LUBRIC", "MOVILIDAD", "RODAMIENT", "AUTOMOTOR"]):
                score += 10

        # Fletes / transporte
        if any(x in nombre for x in ["TRANSP", "FLETE", "LOGIST", "CORREO", "ENVIO", "CADEX", "OCA", "ANDREANI"]):
            if any(x in cuenta_upper for x in ["FLETE", "TRANSP", "MOVILIDAD", "LOGIST"]):
                score += 10

        # Honorarios
        if any(x in nombre for x in ["ESTUDIO", "CONSULT", "ASESOR", "ABOG", "CONTADOR", "NOTAR", "ESCRIBAN"]):
            if any(x in cuenta_upper for x in ["HONOR", "PROFESIONAL", "ASESOR", "SERVICIOS"]):
                score += 10

        # Ferretería / materiales
        if any(x in nombre for x in ["FERRE", "CORRALON", "BULON", "PINTUR", "ELECTRIC", "SANITAR", "MATERIA"]):
            if any(x in cuenta_upper for x in ["MATERIA", "MANTENIMIENTO", "REPARACION", "INSUMOS", "COMPRA"]):
                score += 8

        # Mercaderías / compras
        if any(x in nombre for x in ["MAYORISTA", "COMERCIAL", "DISTRIB", "S.A.", "SRL", "COOP", "VENTAS"]):
            if any(x in cuenta_upper for x in ["COMPRA", "MERCADER", "INSUMOS", "MATERIA PRIMA"]):
                score += 5

        # Bancos / comisiones
        if any(x in nombre for x in ["BANCO", "BBVA", "GALICIA", "SANTANDER", "MACRO", "NACION", "PROVINCIA"]):
            if any(x in cuenta_upper for x in ["GASTOS BANC", "COMISION", "IMPUESTO DEBIT", "FINANCIER"]):
                score += 10

        # Seguros
        if any(x in nombre for x in ["SEGURO", "ASEGURADORA", "SAN CRISTOBAL", "FEDERACION PATRONAL", "SANCOR"]):
            if any(x in cuenta_upper for x in ["SEGURO", "PRIMAS"]):
                score += 10

        # Servicios públicos / telecom
        if any(x in nombre for x in ["EDENOR", "EDESUR", "EDEA", "CAMUZZI", "TELECOM", "MOVISTAR", "CLARO", "PERSON"]):
            if any(x in cuenta_upper for x in ["LUZ", "GAS", "TELEFON", "INTERNET", "SERVICIOS", "COMUNICACIONES"]):
                score += 10

        # Relación con la actividad de la empresa
        if "PISCINA" in actividad or "PISCINAS" in actividad:
            if any(x in nombre for x in ["QUIMIC", "CLORO", "BOMBA", "FILTRO", "PVC", "FERRE", "CORRALON"]):
                if any(x in cuenta_upper for x in ["MATERIA", "INSUMOS", "COMPRA", "MERCADER"]):
                    score += 4

        if score > 0:
            sugerencias.append((codigo, cuenta, score))

    sugerencias = sorted(sugerencias, key=lambda x: x[2], reverse=True)

    # sacar duplicados por código
    sugerencias_unicas = []
    codigos_vistos = set()
    for codigo, cuenta, score in sugerencias:
        if codigo not in codigos_vistos:
            sugerencias_unicas.append((codigo, cuenta, score))
            codigos_vistos.add(codigo)
        if len(sugerencias_unicas) == 3:
            break

    return sugerencias_unicas

def buscar_en_memoria(cuit, memoria_df):
    if memoria_df is None or memoria_df.empty:
        return None

    coincidencias = memoria_df[memoria_df["CUIT"] == cuit].copy()
    if coincidencias.empty:
        return None

    # priorizar la última ocurrencia
    fila = coincidencias.iloc[-1]

    return {
        "Codigo_Cuenta_Final": fila.get("Codigo_Cuenta_Final", ""),
        "Cuenta_Final": fila.get("Cuenta_Final", "")
    }

# =========================
# PROCESO PRINCIPAL
# =========================
if st.button("Procesar imputación"):

    if archivo_padron is None:
        st.error("Falta subir el padrón de proveedores.")
        st.stop()

    if archivo_plan is None:
        st.error("Falta subir el plan de cuentas.")
        st.stop()

    # Leer padrón
    try:
        xl_padron = pd.ExcelFile(archivo_padron)
        if "Padron_Proveedores" in xl_padron.sheet_names:
            padron = pd.read_excel(archivo_padron, sheet_name="Padron_Proveedores")
        else:
            padron = pd.read_excel(archivo_padron)
        padron = normalizar_columnas(padron)
    except Exception as e:
        st.error(f"Error leyendo padrón: {e}")
        st.stop()

    # Leer plan
    try:
        plan = pd.read_excel(archivo_plan)
        plan = normalizar_columnas(plan)
    except Exception as e:
        st.error(f"Error leyendo plan de cuentas: {e}")
        st.stop()

    # Leer memoria
    memoria = None
    if archivo_memoria is not None:
        try:
            memoria = pd.read_excel(archivo_memoria)
            memoria = normalizar_columnas(memoria)
        except Exception as e:
            st.error(f"Error leyendo memoria histórica: {e}")
            st.stop()

    # Detectar columnas padrón
    col_cuit_padron = detectar_columna(padron, ["cuit"])
    col_proveedor_padron = detectar_columna(padron, ["proveedor"])
    col_importe_padron = detectar_columna(padron, ["importe_total", "importe total"])
    col_cantidad_padron = detectar_columna(padron, ["cantidad_comprobantes", "cantidad comprobantes"])

    if col_cuit_padron is None or col_proveedor_padron is None:
        st.error("El padrón debe tener al menos columnas CUIT y Proveedor.")
        st.write("Columnas detectadas en padrón:", padron.columns.tolist())
        st.stop()

    # Detectar columnas plan
    col_codigo_plan = detectar_columna(plan, ["código", "codigo"])
    col_cuenta_plan = detectar_columna(plan, ["cuenta", "nombre"])

    if col_codigo_plan is None or col_cuenta_plan is None:
        st.error("El plan de cuentas debe tener columnas Código y Cuenta.")
        st.write("Columnas detectadas en plan:", plan.columns.tolist())
        st.stop()

    plan = plan[[col_codigo_plan, col_cuenta_plan]].copy()
    plan.columns = ["Código", "Cuenta"]

    # Preparar memoria
    if memoria is not None:
        col_cuit_mem = detectar_columna(memoria, ["cuit"])
        col_proveedor_mem = detectar_columna(memoria, ["proveedor"])
        col_codigo_mem = detectar_columna(memoria, ["codigo_cuenta_final", "código_cuenta_final", "codigo cuenta final"])
        col_cuenta_mem = detectar_columna(memoria, ["cuenta_final", "cuenta final"])

        if col_cuit_mem is None or col_codigo_mem is None or col_cuenta_mem is None:
            st.error("La memoria debe tener columnas CUIT, Codigo_Cuenta_Final y Cuenta_Final.")
            st.write("Columnas detectadas en memoria:", memoria.columns.tolist())
            st.stop()

        memoria = memoria[[col_cuit_mem, col_proveedor_mem, col_codigo_mem, col_cuenta_mem]].copy()
        memoria.columns = ["CUIT", "Proveedor", "Codigo_Cuenta_Final", "Cuenta_Final"]
        memoria["CUIT"] = memoria["CUIT"].apply(limpiar_cuit)

    # Preparar padrón
    base = padron.copy()
    base["CUIT"] = base[col_cuit_padron].apply(limpiar_cuit)
    base["Proveedor"] = base[col_proveedor_padron].astype(str).str.strip()

    if col_importe_padron:
        base["Importe_Total"] = pd.to_numeric(base[col_importe_padron], errors="coerce").fillna(0)
    else:
        base["Importe_Total"] = 0

    if col_cantidad_padron:
        base["Cantidad_Comprobantes"] = pd.to_numeric(base[col_cantidad_padron], errors="coerce").fillna(0)
    else:
        base["Cantidad_Comprobantes"] = 0

    resultados = []

    for _, row in base.iterrows():
        cuit = row["CUIT"]
        proveedor = row["Proveedor"]
        importe_total = row["Importe_Total"]
        cantidad_comprobantes = row["Cantidad_Comprobantes"]

        memoria_match = buscar_en_memoria(cuit, memoria)

        codigo_memoria = ""
        cuenta_memoria = ""
        origen = "REGLAS"
        conflicto = "NO"

        codigo_1 = ""
        cuenta_1 = ""
        codigo_2 = ""
        cuenta_2 = ""
        codigo_3 = ""
        cuenta_3 = ""
        confianza = "Baja"
        fundamento = "Sin coincidencia clara"
        revisar = "SI"

        if memoria_match is not None:
            codigo_memoria = memoria_match["Codigo_Cuenta_Final"]
            cuenta_memoria = memoria_match["Cuenta_Final"]
            origen = "MEMORIA"
            confianza = "Alta"
            fundamento = "Proveedor encontrado en memoria histórica del cliente"
            revisar = "NO"

            # Igual generamos alternativas por reglas para comparar
            sugerencias = sugerir_por_reglas(proveedor, actividad_empresa, plan)

            if len(sugerencias) > 0:
                codigo_1, cuenta_1, _ = sugerencias[0]
            if len(sugerencias) > 1:
                codigo_2, cuenta_2, _ = sugerencias[1]
            if len(sugerencias) > 2:
                codigo_3, cuenta_3, _ = sugerencias[2]

            if codigo_1 != "" and str(codigo_memoria).strip() != str(codigo_1).strip():
                conflicto = "SI"
                revisar = "SI"
                fundamento = "La memoria histórica difiere de la mejor sugerencia automática"

        else:
            sugerencias = sugerir_por_reglas(proveedor, actividad_empresa, plan)

            if len(sugerencias) > 0:
                codigo_1, cuenta_1, _ = sugerencias[0]
            if len(sugerencias) > 1:
                codigo_2, cuenta_2, _ = sugerencias[1]
            if len(sugerencias) > 2:
                codigo_3, cuenta_3, _ = sugerencias[2]

            if len(sugerencias) == 0:
                confianza = "Baja"
                fundamento = "No se encontraron coincidencias por reglas"
                revisar = "SI"
            elif len(sugerencias) == 1:
                confianza = "Media"
                fundamento = "Se encontró una coincidencia probable por reglas"
                revisar = "SI"
            else:
                confianza = "Media"
                fundamento = "Se encontraron múltiples coincidencias probables por reglas"
                revisar = "SI"

        resultados.append({
            "CUIT": cuit,
            "Proveedor": proveedor,
            "Importe_Total": importe_total,
            "Cantidad_Comprobantes": cantidad_comprobantes,
            "Codigo_Cuenta_Memoria": codigo_memoria,
            "Cuenta_Memoria": cuenta_memoria,
            "Codigo_Cuenta_Sugerida_1": codigo_1,
            "Cuenta_Sugerida_1": cuenta_1,
            "Codigo_Cuenta_Sugerida_2": codigo_2,
            "Cuenta_Sugerida_2": cuenta_2,
            "Codigo_Cuenta_Sugerida_3": codigo_3,
            "Cuenta_Sugerida_3": cuenta_3,
            "Origen": origen,
            "Confianza": confianza,
            "Conflicto": conflicto,
            "Fundamento": fundamento,
            "Cuenta_Final": "",
            "Codigo_Cuenta_Final": "",
            "Validado": "NO",
            "Revisar": revisar
        })

    df_resultado = pd.DataFrame(resultados)

    conflictos = df_resultado[
        (df_resultado["Conflicto"] == "SI") |
        (df_resultado["Revisar"] == "SI")
    ].copy()

    # =========================
    # EXPORTAR
    # =========================
    output_path = os.path.join(tempfile.gettempdir(), "padron_imputado_cliente.xlsx")

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df_resultado.to_excel(writer, sheet_name="Padron_Imputado", index=False)
        conflictos.to_excel(writer, sheet_name="Conflictos", index=False)

        workbook = writer.book
        formato_num = workbook.add_format({"num_format": '#,##0.00;-#,##0.00;-'})

        ws1 = writer.sheets["Padron_Imputado"]
        ws2 = writer.sheets["Conflictos"]

        # Ajuste de anchos
        for idx, col in enumerate(df_resultado.columns):
            ancho = max(14, min(35, len(str(col)) + 2))
            if col == "Importe_Total":
                ws1.set_column(idx, idx, 16, formato_num)
            else:
                ws1.set_column(idx, idx, ancho)

        for idx, col in enumerate(conflictos.columns):
            ancho = max(14, min(35, len(str(col)) + 2))
            if col == "Importe_Total":
                ws2.set_column(idx, idx, 16, formato_num)
            else:
                ws2.set_column(idx, idx, ancho)

    with open(output_path, "rb") as f:
        st.download_button(
            "📥 Descargar padrón imputado",
            f,
            file_name="padron_imputado_cliente.xlsx"
        )

    st.success(f"✅ Proceso completo. Proveedores procesados: {len(df_resultado)}")
