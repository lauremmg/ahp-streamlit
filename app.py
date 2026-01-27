import streamlit as st
import numpy as np
import pandas as pd
import sqlite3
import itertools
import uuid
import os

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(
    page_title="Encuesta AHP – Café Arábigo",
    layout="wide"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "database.db")

os.makedirs(DATA_DIR, exist_ok=True)

# =====================================================
# AHP – CONSISTENCY RATIO
# =====================================================
RI = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
    6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49
}

def calculate_cr(matrix):
    matrix = np.array(matrix)
    n = matrix.shape[0]
    eigvals, _ = np.linalg.eig(matrix)
    lambda_max = max(eigvals.real)
    CI = (lambda_max - n) / (n - 1)
    CR = CI / RI[n] if n in RI else 0
    return round(CR, 4)

# =====================================================
# DATABASE
# =====================================================
def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_db() as con:
        cur = con.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS criteria (
            project_id TEXT,
            name TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            user_name TEXT,
            cr REAL,
            file_path TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS matrices (
        response_id TEXT,
        i INTEGER,
        j INTEGER,
        value REAL
        )
        """)


        con.commit()


init_db()

# =====================================================
# ROUTING LOGIC
# =====================================================
project_id = st.query_params.get("project_id", None)

# =====================================================
# ADMIN – CREATE PROJECT
# =====================================================
if project_id is None:

    st.title("Administrador – Crear Encuesta AHP")

    project_name = st.text_input("Nombre del proyecto")
    n_criteria = st.number_input(
        "Número de criterios",
        min_value=2,
        max_value=10,
        step=1
    )

    criteria = []
    for i in range(int(n_criteria)):
        criteria.append(
            st.text_input(f"Criterio {i+1}")
        )

    if st.button("Crear proyecto"):
        if not project_name or not all(criteria):
            st.error("Complete todos los campos")
            st.stop()

        pid = str(uuid.uuid4())

        with get_db() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO projects VALUES (?, ?)",
                (pid, project_name)
            )
            for c in criteria:
                cur.execute(
                    "INSERT INTO criteria VALUES (?, ?)",
                    (pid, c)
                )
            con.commit()

        st.success("Proyecto creado correctamente")

        APP_URL = "ahp-app-encuestacafearabigo.streamlit.app"
        st.code(f"{APP_URL}/?project_id={pid}")

        st.info("Este enlace es el que debe enviar a los encuestados.")

st.divider()
st.subheader("📥 Descargar resultados de encuestas")

with get_db() as con:
    cur = con.cursor()
    cur.execute("SELECT id, name FROM projects")
    projects = cur.fetchall()

if projects:
    project_map = {name: pid for pid, name in projects}
    selected_project = st.selectbox(
        "Seleccione un proyecto",
        list(project_map.keys())
    )

    selected_pid = project_map[selected_project]

    with get_db() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, user_name, cr
            FROM responses
            WHERE project_id=?
        """, (selected_pid,))
        responses = cur.fetchall()

    if responses:
        st.success(f"Se encontraron {len(responses)} respuestas")

        # -------- DESCARGA INDIVIDUAL --------
        response_map = {
            f"{user} (CR={round(cr,3)})": rid
            for rid, user, cr in responses
        }

        selected_response = st.selectbox(
            "Descargar respuesta individual",
            list(response_map.keys())
        )

        rid = response_map[selected_response]

        with get_db() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT name FROM criteria WHERE project_id=?
            """, (selected_pid,))
            criteria = [c[0] for c in cur.fetchall()]

            cur.execute("""
                SELECT i, j, value
                FROM matrices
                WHERE response_id=?
            """, (rid,))
            data = cur.fetchall()

        size = len(criteria)
        matrix = np.ones((size, size))

        for i, j, v in data:
            matrix[i][j] = v

        df_matrix = pd.DataFrame(matrix, index=criteria, columns=criteria)

        cur.execute("SELECT cr FROM responses WHERE id=?", (rid,))
        cr_value = cur.fetchone()[0]

        df_cr = pd.DataFrame({"CR": [cr_value]})

        import io
        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_matrix.to_excel(writer, sheet_name="Matriz_AHP")
            df_cr.to_excel(writer, sheet_name="Consistencia", index=False)

        st.download_button(
            "📄 Descargar Excel individual",
            data=buffer.getvalue(),
            file_name=f"Respuestas_{selected_response}.xlsx"
        )

        # -------- ZIP CON TODAS LAS RESPUESTAS --------
        st.divider()
        st.subheader("📦 Descargar TODAS las respuestas")

        import zipfile
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w") as zipf:
            for rid, user, cr in responses:
                with get_db() as con:
                    cur = con.cursor()
                    cur.execute("""
                        SELECT i, j, value
                        FROM matrices
                        WHERE response_id=?
                    """, (rid,))
                    data = cur.fetchall()

                matrix = np.ones((size, size))
                for i, j, v in data:
                    matrix[i][j] = v

                df_m = pd.DataFrame(matrix, index=criteria, columns=criteria)
                df_c = pd.DataFrame({"CR": [cr]})

                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    df_m.to_excel(writer, sheet_name="Matriz_AHP")
                    df_c.to_excel(writer, sheet_name="Consistencia", index=False)

                zipf.writestr(
                    f"Respuestas_{user}.xlsx",
                    buf.getvalue()
                )

        st.download_button(
            "⬇️ Descargar ZIP con todas las matrices",
            data=zip_buffer.getvalue(),
            file_name=f"Resultados_{selected_project}.zip"
        )

    else:
        st.warning("Este proyecto aún no tiene respuestas.")
else:
    st.info("No hay proyectos creados todavía.")


# =====================================================
# RESPONDENT – SURVEY
# =====================================================
    st.title("Encuesta AHP – Café Arábigo")

    st.markdown("""
    El Proceso Analítico Jerárquico (AHP) es un método multicriterio ampliamente utilizado para la toma de decisiones complejas, 
    permitiendo comparar variables de forma estructurada y consistente, transformando juicios expertos en resultados cuantitativos confiables.
    
    El objetivo de esta encuesta es determinar el peso relativo de las variables que influyen en la aptitud del cultivo de café arábigo, 
    considerando factores climatológicos, topográficos, edáficos y socioeconómicos.

    **Instrucciones**
    La evaluación se realiza mediante comparaciones por pares. En cada fila se presentan dos criterios, usted debe:
    1. Seleccionar cuál criterio es más importante
    2. Indicar la intensidad de preferencia (escala 1–9 de Saaty)
    
    **Escala AHP**  
    1 = Igual · 3 = Moderada · 5 = Fuerte · 7 = Muy fuerte · 9 = Extrema  
    (Los valores pares representan intensidades intermedias)
    """)

    user_name = st.text_input("Ingrese su nombre")

    pairs = list(itertools.combinations(range(len(criteria)), 2))
    matrix = np.ones((len(criteria), len(criteria)))

    st.subheader("Comparaciones por pares")

    for i, j in pairs:
        c1, c2, c3 = st.columns([4, 4, 3])

        with c1:
            choice = st.selectbox(
                f"{criteria[i]} vs {criteria[j]}",
                ["", criteria[i], criteria[j]],
                key=f"c_{i}_{j}"
            )

        with c2:
            value = st.selectbox(
                "Intensidad",
                ["", 1, 2, 3, 4, 5, 6, 7, 8, 9],
                key=f"v_{i}_{j}"
            )

        if choice and value:
            if choice == criteria[i]:
                matrix[i][j] = value
                matrix[j][i] = 1 / value
            else:
                matrix[j][i] = value
                matrix[i][j] = 1 / value

    if st.button("Enviar encuesta"):
    if not user_name:
        st.error("Ingrese su nombre")
        st.stop()

    # 1️⃣ Calcular CR
    cr = calculate_cr(matrix)

    # 2️⃣ Guardar respuesta y matriz en la BD
    response_id = str(uuid.uuid4())

    with get_db() as con:
        cur = con.cursor()

        # Guardar respuesta
        cur.execute("""
            INSERT INTO responses VALUES (?,?,?,?,?)
        """, (
            response_id,
            project_id,
            user_name,
            cr,
            None
        ))

        # Guardar matriz COMPLETA
        for i in range(len(criteria)):
            for j in range(len(criteria)):
                cur.execute("""
                    INSERT INTO matrices VALUES (?,?,?,?)
                """, (
                    response_id,
                    i,
                    j,
                    float(matrix[i][j])
                ))

        con.commit()

    # 3️⃣ Mostrar resultado al usuario
    st.success("Encuesta enviada correctamente. Gracias por su participación.")
    st.metric("Consistency Ratio (CR)", cr)

    # 4️⃣ Excel SOLO para el usuario (opcional)
    df_matrix = pd.DataFrame(matrix, index=criteria, columns=criteria)
    df_cr = pd.DataFrame({"CR": [cr]})

    import io
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_matrix.to_excel(writer, sheet_name="Matriz_AHP")
        df_cr.to_excel(writer, sheet_name="Consistencia", index=False)

    st.download_button(
        "Descargar su matriz AHP",
        data=buffer.getvalue(),
        file_name=f"Matriz_AHP_{user_name}.xlsx"
    )

