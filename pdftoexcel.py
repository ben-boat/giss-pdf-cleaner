import streamlit as st
import pandas as pd
import camelot
import tempfile
import os

def clean_pdf(uploaded_file):
    """Take an uploaded PDF, clean it, and return the path to the Excel file."""

    # --- Save uploaded PDF temporarily ---
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    # --- Extract tables from PDF ---
    tables = camelot.read_pdf(tmp_path, pages="all")
    df_list = [t.df for t in tables]
    df = pd.concat(df_list, ignore_index=True)

    # --- Keep only first 10 columns ---
    df = df.iloc[:, :10]

    # --- Rename columns ---
    df.columns = [
        "No.",
        "Value Date",
        "Tran Type",
        "Tran Ref",
        "Participant",
        "Additional Information",
        "DR",
        "Amount_DR",
        "CR",
        "Amount_CR"
    ]

    # --- Step 1: Remove rows containing "table from page" ---
    df = df[~df.apply(lambda row: row.astype(str).str.contains("table from page", case=False).any(), axis=1)]

    # --- Step 2: Drop completely empty rows ---
    df = df.dropna(how="all")
    df = df[~(df.apply(lambda row: (row.astype(str).str.strip() == "").all(), axis=1))]

    # --- Step 3: Drop rows where column A contains "Additional" ---
    df = df[~df.iloc[:, 0].astype(str).str.contains("Additional", case=False, na=False)]

    # --- Step 4: Fix continuation rows (only column F has value) ---
    rows_to_drop = []
    for i in range(1, len(df)):
        row = df.iloc[i]
        non_empty = row.astype(str).str.strip() != ""
        if non_empty.sum() == 1 and non_empty.iloc[5]:
            df.iat[i-1, 5] = str(df.iat[i-1, 5]) + " " + str(row.iloc[5])
            rows_to_drop.append(df.index[i])
    df = df.drop(rows_to_drop)

    # --- Step 5: Convert target columns to numeric ---
    num_cols = ["DR", "Amount_DR", "CR", "Amount_CR", "No.", "Tran Type"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "").str.strip(), errors="coerce")

    # --- Step 6: Convert Value Date to datetime ---
    df["Value Date"] = pd.to_datetime(df["Value Date"], errors="coerce", dayfirst=True).dt.date

    # --- Create Debit sheet (if column G not empty) ---
    df_debit = df[df.iloc[:, 6].notna()].copy()
    df_debit = df_debit.sort_values(by=df.columns[7], ascending=True)

    debit_total = {
        df.columns[0]: "TOTAL",
        df.columns[6]: df_debit.iloc[:, 6].count(),
        df.columns[7]: df_debit.iloc[:, 7].sum()
    }
    df_debit = pd.concat([df_debit, pd.DataFrame([debit_total])], ignore_index=True)
    df_debit = df_debit.drop(columns=[df.columns[8], df.columns[9]])

    # --- Create Credit sheet (if column I not empty) ---
    df_credit = df[df.iloc[:, 8].notna()].copy()
    df_credit = df_credit.sort_values(by=df.columns[9], ascending=True)

    credit_total = {
        df.columns[0]: "TOTAL",
        df.columns[8]: df_credit.iloc[:, 8].count(),
        df.columns[9]: df_credit.iloc[:, 9].sum()
    }
    df_credit = pd.concat([df_credit, pd.DataFrame([credit_total])], ignore_index=True)
    df_credit = df_credit.drop(columns=[df.columns[6], df.columns[7]])

    # --- Reset index ---
    df = df.reset_index(drop=True)

    # --- Construct Excel filename based on uploaded PDF ---
    pdf_name = os.path.splitext(uploaded_file.name)[0]  # removes ".pdf"
    output_path = os.path.join(tempfile.gettempdir(), f"{pdf_name}_clean.xlsx")

    # --- Save to Excel ---
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Cleaned", index=False)
        df_debit.to_excel(writer, sheet_name="Debit", index=False)
        df_credit.to_excel(writer, sheet_name="Credit", index=False)

    return output_path, df  # also return df for preview

# ================== STREAMLIT APP ==================

st.title("📑 PDF to Excel Cleaner")

uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

if uploaded_file:
    if st.button("Process PDF"):
        with st.spinner("Processing..."):
            excel_path, cleaned_df = clean_pdf(uploaded_file)

        st.success("✅ Cleaning done!")

        # Preview first 10 rows of cleaned sheet
        st.subheader("Preview of Cleaned Sheet (first 10 rows)")
        st.dataframe(cleaned_df.head(10))

        # Provide download button
        with open(excel_path, "rb") as f:
            st.download_button(
                label="Download Cleaned Excel",
                data=f,
                file_name=os.path.basename(excel_path),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
