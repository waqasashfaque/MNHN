import streamlit as st
import pandas as pd
import numpy as np
import re
import requests
from io import BytesIO
import plotly.express as px

st.set_page_config(layout="wide", page_title="MNHN Dashboard")
# Adding all users, all users will be appear as dropdown 
USERS = st.secrets["users"]

def login_form():
    st.title("Login")
    usernames = list(USERS.keys())
    username = st.selectbox("Select Username", usernames)
    password = st.text_input("Password", type="password")
    login_btn = st.button("Login")
    if login_btn:
        if username in USERS and password == USERS[username]:
            st.session_state['auth'] = True
            st.session_state['username'] = username
            st.rerun()
        else:
            st.error("Invalid credentials!")

if not st.session_state.get('auth', False):
    login_form()
    st.stop()
    
# Load data from Google Drive Excel
@st.cache_data
def load_data():
    file_id = st.secrets["id"]
    gdrive_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(gdrive_url)
    xls = pd.ExcelFile(BytesIO(response.content))
    data = xls.parse("Database")
    key = xls.parse("Key")
    try:
        key_mrq = xls.parse("Key_MRQ")
        mrq_text_dict = dict(zip(key_mrq['Variable'], key_mrq['TEXT']))
    except Exception as e:
        st.warning(f"Key_MRQ sheet not loaded: {str(e)}")
        mrq_text_dict = {}
    return data, key, mrq_text_dict
if st.button("🔄 Sync Latest Data"):
    st.cache_data.clear()
    st.success("Data refreshed from Google Drive! Please wait...")
    st.rerun()
    
data, key, mrq_text_dict = load_data()
rename_dict = dict(zip(key['Variables'], key['TEXT']))

#Converting Age of child into Age classes:
# Make sure cb4 is numeric (will convert errors to NaN)
data['cb4'] = pd.to_numeric(data['cb4'], errors='coerce')
# Drop missing/NaN if required or handle as needed
data = data.dropna(subset=['cb4'])
bins = [-1, 3, 7, 11]
labels = ['0 - 3 Months', '4 - 7 Months', '8 - 11 Months']
data['cb4_class'] = pd.cut(data['cb4'], bins=bins, labels=labels)

#AC2 no of visits converted 8 and above in one class
data['AC2'] = pd.to_numeric(data['AC2'], errors='coerce').fillna(0).astype(int)
# Helper function for labeling
def ac2_group(val):
    if val >= 8:
        return '8 and above'
    else:
        return str(val)

# New Variable AC2_new
data['AC2_new'] = data['AC2'].apply(ac2_group)

# --- Identify Multiple Selection Variables ---

import re
# --- Multiple Selection Variable Groups ---

multi_select_groups = {}
for col in data.columns:
    match = re.match(r"(.*)_(\d+)$", col)
    if match:
        prefix = match.group(1)
        multi_select_groups.setdefault(prefix, []).append(col)

# --- Function to generate summary charts and tables ---
def summary_charts_tables(data, var_list, mappings, module_key):
    for var in single_cats:
            if var in data.columns:
                # Get descriptive title from mapping
                var_title = mrq_text_dict.get(var, rename_dict.get(var, var))
                
                # Group by variable and district for grouped bar chart
                group_df = data.groupby([var, 'District']).size().reset_index(name='Count')
                fig = px.bar(group_df, x=var, y='Count', color='District', barmode='group',
                            labels={var: var_title, 'Count': 'Count', 'District': 'District'},
                            title=var_title)
                fig.update_layout(title={'text': var_title, 'font': {'size': 32}})
                fig.update_layout(
                dragmode=False,  # Disable zooming and panning
                xaxis=dict(fixedrange=True),  # Disable x-axis zooming
                yaxis=dict(fixedrange=True)  # Disable y-axis zooming
            )            
                st.plotly_chart(fig, use_container_width=True)

                # Build N and % table for each district and total
                districts_list = sorted(data['District'].dropna().unique())
                count_table = data.pivot_table(index=var, columns='District', aggfunc='size', fill_value=0)
                count_table['Total'] = count_table.sum(axis=1)
                # Calculate column totals for N
                col_totals = count_table.sum(axis=0)
                # Calculate % table
                percent_table = count_table.div(col_totals, axis=1).fillna(0) * 100
                percent_table = percent_table.round(1)
                # Interleave N and % columns
                columns_n_pct = []
                for col in districts_list + ['Total']:
                    columns_n_pct.append((col, 'N'))
                    columns_n_pct.append((col, '%'))
                # Build final DataFrame
                final_rows = []
                for idx in count_table.index:
                    row = []
                    for col in districts_list + ['Total']:
                        row.append(count_table.loc[idx, col])
                        row.append(f"{percent_table.loc[idx, col]:.1f}%")
                    final_rows.append([idx] + row)
                # Add total row
                total_row = ['Total']
                for col in districts_list + ['Total']:
                    total_row.append(col_totals[col])
                    total_row.append("100.0%")
                final_rows.append(total_row)
                # Build columns
                columns = [''] + [item for col in districts_list + ['Total'] for item in (col, '')]
                # Build multi-header HTML
                def render_n_pct_table(columns, rows, var_title):
                    header_color = "#2905f5"
                    total_color =  "#5337f3"
                    html = '<style>\n'
                    html += 'table.customtbl {border-collapse: collapse; width: 100%;}' + '\n'
                    html += 'table.customtbl th {background: %s; font-weight: bold; border: 1px solid #aaa; padding: 6px;}' % header_color + '\n'
                    html += 'table.customtbl td {border: 1px solid #aaa; padding: 6px;}' + '\n'
                    html += '</style>\n'
                    html += f'<table class="customtbl">\n'
                    # First header row
                    html += '<tr><th rowspan="2">{}</th>'.format(var_title)
                    for col in districts_list + ['Total']:
                        html += f'<th colspan="2">{col}</th>'
                    html += '</tr>\n'
                    # Second header row
                    html += '<tr>'
                    for _ in districts_list + ['Total']:
                        html += '<th>N</th><th>%</th>'
                    html += '</tr>\n'
                    # Data rows
                    for row in rows:
                        is_total_row = str(row[0]).lower() == 'total'
                        html += '<tr>'
                        # Row label
                        if is_total_row:
                            html += f'<td style="font-weight:bold;background:{total_color}">{row[0]}</td>'
                        else:
                            html += f'<td style="font-weight:bold">{row[0]}</td>'
                        # Row values
                        for i, val in enumerate(row[1:]):
                            is_total_col = (i // 2 == len(districts_list))
                            cell_style = ''
                            if is_total_row or is_total_col:
                                cell_style = f'font-weight:bold;background:{total_color}'
                            html += f'<td style="{cell_style}">{val}</td>'
                        html += '</tr>\n'
                    html += '</table>'
                    return html

                st.markdown(render_n_pct_table(columns, final_rows, var_title), unsafe_allow_html=True)

                # Download as CSV (matching the HTML table)
                import csv
                import io
                csv_buffer = io.StringIO()
                # Write header rows
                writer = csv.writer(csv_buffer)
                # First header row
                header_row1 = [var_title]
                for col in districts_list + ['Total']:
                    header_row1.extend([col, ''])
                writer.writerow(header_row1)
                # Second header row
                header_row2 = [''] + [item for _ in districts_list + ['Total'] for item in ('N', '%')]
                writer.writerow(header_row2)
                # Data rows
                for row in final_rows:
                    writer.writerow(row)
                csv_data = csv_buffer.getvalue().encode('utf-8')
                st.download_button(
                    label="Download table as CSV",
                    data=csv_data,
                    file_name=f"{var_title}_table.csv",
                    mime="text/csv"
                )


# --- KPIs ---
st.title("📊 Endline Assessment of MNHN Program using the NIMS toolkit (Nutrition Intervention Monitoring Surveys (NIMS)")
st.info(f"You are logged in as: {st.session_state['username']}")
#st.markdown("---")
#st.markdown("#### District Filter")
districts = sorted(data["District"].dropna().unique())
default_selection = districts  # Select all by default

selected_districts = st.multiselect(
    "Select one or more districts to analyze", 
    options=districts,
    default=default_selection,
    help="Select one or more districts to analyze"
)

# Apply district filter
if selected_districts:
    data = data[data["District"].isin(selected_districts)]
else:
    data = data


district_display = "All Districts" if len(selected_districts) == len(districts) else ", ".join(selected_districts)
col1, col2 = st.columns([5, 2])  # left/right column sizes
with col1:
    st.subheader(f"Districts: {district_display}")
with col2:
    st.markdown(f"<div style='text-align: right; font-size: 1.3em; font-weight: bold;'>Total Interviews: {len(data)}</div>", unsafe_allow_html=True)
st.caption(f"🔄 All Charts are dynamically updated based on your selected District(s): {district_display}")
# --- Load and process data ---

# --- Step 1: To add all modules of the dashbaord.

modules = [
    "EXECUTIVE SUMMARY",
    "Module : Basic Information",
    "BACKGROUND MODULE: INFANT/CHILD",
    "MODULE 1: ANC",
    "MODULE 2: IRON/IRON AND FOLIC ACID CONTAINING SUPPLEMENTS",
    "MODULE 3: IFA BCI",
    "MODULE 4: SKILLED BIRTH ATTENDANCE & CARE POST-DELIVERY",
    "MODULE 5: BREAST FEEDING",
    "MODULE 6: COUNSELLING IYCF",
    "MODULE 7: BENEFICIARY KNOWLEDGE – BREAST FEEDING",
    "MODULE 8: KANGAROO CARE",
    "MODULE 9: WORK AND TIME USAGE QUESTIONS",
    "MODULE 10: New Gender questions for endline",
    "Analysis of Multi-Response Variables"
]
st.markdown("""
    <style>
    div[role="radiogroup"] > label, div[role="radiogroup"] > div > label {
        font-size: 22px!important;
        font-weight: bold!important;
    }
    </style>
""", unsafe_allow_html=True)

# --- Step 2: Select a Module #
active_module = st.radio("Select Module from the following to see the insights", modules, horizontal=True)  # Horizontal buttons
st.header(f"📊 {active_module}")
if active_module == "EXECUTIVE SUMMARY":
    st.markdown("---")
    st.markdown("""
<style>
    .section-heading {font-size: 36pt;font-weight: bold;    }
    .paragraph-text {font-size: 24pt;text-align: justify;line-height: 1;margin-bottom: 0px;}
    .bullet-points {line-height: 1;margin-bottom: 0px;padding-left: 20px;}
    .bullet-points li {argin-bottom: 0px;}
</style>

<div class="section-heading">📑 EXECUTIVE SUMMARY</div>
<div class="paragraph-text">
The endline survey findings reflect notable improvements in the receipt and consumption of iron and folic acid (IFA) supplements across all surveyed districts, while antenatal care (ANC) utilization demonstrated a more mixed performance. The percentage of women receiving at least 90 IFA tablets increased significantly, particularly in Lodhran, where it rose dramatically from 7% at baseline to 79% at endline. Overall, the proportion of women who consumed any IFA increased from 87% to 98%, and those consuming at least 90 tablets rose from 41% to 69%. Awareness of the benefits of IFA supplementation during pregnancy also improved, with knowledge levels increasing from 70% to 84% across the districts.<br><br>

In terms of ANC utilization, the coverage of ANC in the first trimester improved from 81% to 91%, indicating better early engagement with maternal health services. However, ANC coverage for eight or more visits, captured only in the endline, remained low at 21%, with Khairpur (22%) and Lodhran (26%) showing better performance. The proportion of women making at least four ANC visits saw a slight overall decline from 66% to 64%, mainly due to a sharp drop in Jamshoro. Furthermore, the percentage of women who had at least one ANC visit also decreased from 98% to 91%, with the lowest levels recorded in Jamshoro.<br><br>

Behavior change communication efforts had mixed outcomes. Although overall awareness of anemia symptoms increased from 82% to 89%, and knowledge about IFA supplementation improved, exposure to behavior change interventions (BCIs) specifically targeting daily IFA use declined in districts like Jamshoro and Khairpur. This suggests a need to re-strengthen community-level educational outreach and support systems to sustain progress.<br><br>

Progress was also recorded in essential newborn care practices. Early initiation of breastfeeding increased from 53% to 61%, with the most significant gains seen in Khairpur, while Lodhran experienced a slight decline. Deliveries attended by skilled birth attendants improved overall. However, there was a notable drop in optimal timing of cord clamping, falling from 70% at baseline to just 26% at endline, with major declines observed in Lodhran and Jamshoro. On a positive note, skin-to-skin contact after birth improved across districts, especially in Khairpur. Awareness of timely breastfeeding initiation also increased from 62% to 87%, reinforcing the impact of maternal health education initiatives.<br><br>

The percentage of women with decision-making power over their health and nutrition services was highest in Lodhran (56%). Financial decision-making remained low across all districts, with only 5% of women reporting control over financial resources related to healthcare. Awareness of health rights was highest in Khairpur (60%), indicating systemic barriers preventing women from accessing proper care.<br><br>

Stock shortages of IFA supplements have improved significantly among most districts. The overall stockout rate dropped from 83% at baseline to 41% in the last three months, with Lodhran showing the best supply availability (only 17% experiencing shortages). Over the past year, stock availability improved, with only 13% of facilities experiencing stock outs, compared to 80% at the baseline.
</div>

<br>

<div class="section-heading">GENERAL RECOMMENDATIONS:</div>
<ul class="bullet-points">
    <li><span style="font-size:24pt;">Targeted health campaigns require to focus on Jamshoro.</span></li>
    <li><span style="font-size:24pt;">Promoting ANC utilization with encouraging ≥4 ANC visits.</span></li>
    <li><span style="font-size:24pt;">Improving the birth practices through training providers on skilled attendance and cord clamping.</span></li>
    <li><span style="font-size:24pt;">Enhancing community awareness by boosting IFA knowledge and breastfeeding practices.</span></li>
    <li><span style="font-size:24pt;">Supply chain strengthening through ensuring IFA supplement availability.</span></li>
</ul>
""", unsafe_allow_html=True
)


#Basic Information

# --- Module : Basic Information ---
elif active_module == "Module : Basic Information":
    st.markdown("---")
    #st.header("📊 BASIC INFORMATION")
    single_cats = ['Cluster_Area','MB3','MB4', 'MB5']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "Basic_Info")

# --- BACKGROUND MODULE: INFANT/CHILD ---

elif active_module == "BACKGROUND MODULE: INFANT/CHILD":
    st.markdown("---")
    #st.header("📊 BACKGROUND MODULE: INFANT/CHILD")
    single_cats = ['cb2','cb4_class']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "Background_Child")

# --- "MODULE 1: ANC ---
elif active_module == "MODULE 1: ANC":
    st.markdown("---")
    #st.header("📊 MODULE 1: ANC")
    single_cats = ['AC1','AC2_new', 'AC5','AC7']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "ANC")


# --- MODULE 2: IRON/IRON AND FOLIC ACID CONTAINING SUPPLEMENTS ---
elif active_module == "MODULE 2: IRON/IRON AND FOLIC ACID CONTAINING SUPPLEMENTS":
    st.markdown("---")
    #st.header("📊 MODULE 2: IRON/IRON AND FOLIC ACID CONTAINING SUPPLEMENTS")
    single_cats = ['IF1','IF2']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "Iron_Supplement")

# --- MODULE 3: IFA BCI ---
elif active_module == "MODULE 3: IFA BCI":
    st.markdown("---")
    #st.header("📊 MODULE 3: IFA BCI")
    single_cats = ['BC1','BC4', 'BC40']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "IFA_BCI")

# --- MODULE 4: SKILLED BIRTH ATTENDANCE & CARE POST-DELIVERY---
elif active_module == "MODULE 4: SKILLED BIRTH ATTENDANCE & CARE POST-DELIVERY":
    st.markdown("---")
    #st.header("📊 MODULE 4: SKILLED BIRTH ATTENDANCE & CARE POST-DELIVERY (BP ODK tool)")
    single_cats = ['SB1','SB1_A1','SB1_A2','SB1_A3','SB3','SB4','SB5']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "SBA_Care")

# --- MODULE 5: BREAST FEEDING ---
elif active_module == "MODULE 5: BREAST FEEDING":
    st.markdown("---")
    #st.header("📊 MODULE 5: BREAST FEEDING ")
    single_cats = ['BF1','BF2','BF4','BF6','BF8','BF9']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "BreastFeeding")

# ---  MODULE 6: COUNSELLING IYCF ---
elif active_module == "MODULE 6: COUNSELLING IYCF":
    st.markdown("---")
    #st.header("📊 MODULE 6: COUNSELLING IYCF")
    single_cats = ['CL1']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "Counselling_IYCF")

# --- MODULE 7: BENEFICIARY KNOWLEDGE – BREAST FEEDING ---
elif active_module == "MODULE 7: BENEFICIARY KNOWLEDGE – BREAST FEEDING":
    st.markdown("---")
    #st.header("📊 MODULE 7: BENEFICIARY KNOWLEDGE – BREAST FEEDING")
    single_cats = ['BKB1','BKB2']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "Beneficiary_Knowledge_BF")

# --- MODULE 8: KANGAROO CARE ---
elif active_module == "MODULE 8: KANGAROO CARE":
    st.markdown("---")
    #st.header("📊 MODULE 8: KANGAROO CARE")
    single_cats = ['KC2','KC3','KC4','KC5','KC6','KC8']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "KangarooCare")

# --- MODULE 9: WORK AND TIME USAGE QUESTIONS ---
elif active_module == "MODULE 9: WORK AND TIME USAGE QUESTIONS":
    st.markdown("---")
    #st.header("📊 MODULE 9: WORK AND TIME USAGE QUESTIONS")
    single_cats = ['WT1','WT8']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "Work_Time")

# --- MODULE 10: New Gender questions for endline ---
elif active_module == "MODULE 10: New Gender questions for endline":
    st.markdown("---")
    #st.header("📊 MODULE 10: New Gender questions for endline ")
    single_cats = ['GE1','GE2','GE3','GE4','GE5_A','GE5_B','GE5_C','GE5_D','GE5_E']  # Add more short codes from your data
    summary_charts_tables(data, single_cats, mrq_text_dict, "Endline_Gender")

# --- Analysis of Multi-Response Variables ---
elif active_module == "Analysis of Multi-Response Variables":
    st.markdown("---")
    #st.header("📊 Analysis of Multi-Response Variables")

    for prefix, columns in multi_select_groups.items():
        main_question = mrq_text_dict.get(prefix, rename_dict.get(prefix, prefix))
        # Option labels nikal lo
        option_labels = [mrq_text_dict.get(col, rename_dict.get(col, col)) for col in columns]
        st.subheader(main_question)

        # Data clean kar lo (numeric)
        for col in columns:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')

        # Plotly chart
        records = []
        districts_list = sorted(data['District'].dropna().unique())
        for col, label in zip(columns, option_labels):
            if col in data.columns:
                selected_mask = data[col].apply(lambda x: str(x).strip().lower() in ['1', 'yes', 'true']) | (data[col] == 1)
                for district in districts_list:
                    count = ((data['District'] == district) & selected_mask).sum()
                    records.append({'Option': label, 'District': district, 'Count': count})
        multi_df = pd.DataFrame(records)
        if not multi_df.empty:
            fig = px.bar(multi_df, x='Option', y='Count', color='District', barmode='group',
                        title=main_question)
            st.plotly_chart(fig, use_container_width=True)

            # Multi-response Table: Correct N & % calculation
            table = pd.DataFrame(index=option_labels, columns=districts_list)
            for label, col in zip(option_labels, columns):
                if col in data.columns:
                    selected_mask = data[col].apply(lambda x: str(x).strip().lower() in ['1', 'yes', 'true']) | (data[col] == 1)
                    for district in districts_list:
                        table.loc[label, district] = ((data['District'] == district) & selected_mask).sum()
            table['Total'] = table.sum(axis=1)

            # Prepare rows: N & Percentage (using unique base row for each district)
            final_rows = []
            for idx in table.index:
                row = [idx]
                for col in districts_list:
                    n = table.loc[idx, col]
                    base_n = (data[data['District'] == col][columns].sum(axis=1) > 0).sum()
                    pct = (n / base_n * 100) if base_n > 0 else 0
                    row.append(n)
                    row.append(f"{pct:.1f}%")
                n_total = table.loc[idx, 'Total']
                base_total = (data[columns].sum(axis=1) > 0).sum()
                pct_total = (n_total / base_total * 100) if base_total > 0 else 0
                row.append(n_total)
                row.append(f"{pct_total:.1f}%")
                final_rows.append(row)

            # SPSS-style Total row - unique count base, one-time at end
            total_row = ['Total']
            for col in districts_list:
                base_n = (data[data['District'] == col][columns].sum(axis=1) > 0).sum()
                total_row.append(base_n)
                total_row.append("100.0%")
            base_all = (data[columns].sum(axis=1) > 0).sum()
            total_row.append(base_all)
            total_row.append("100.0%")
            final_rows.append(total_row)

            # Build columns for display
            columns_table = [''] + [x for col in districts_list + ['Total'] for x in (col, '')]        
            # Styled HTML table
            def render_n_pct_table(columns, rows, var_title):
                header_color = "#2905f5"
                total_color =  "#5337f3"
                html = '<style>\n'
                html += 'table.customtbl {border-collapse: collapse; width: 100%;}' + '\n'
                html += 'table.customtbl th {background: %s; font-weight: bold; border: 1px solid #aaa; padding: 6px;}' % header_color + '\n'
                html += 'table.customtbl td {border: 1px solid #aaa; padding: 6px;}' + '\n'
                html += '</style>\n'
                html += f'<table class="customtbl">\n'
                # First header row
                html += '<tr><th rowspan="2">{}</th>'.format(var_title)
                for col in districts_list + ['Total']:
                    html += f'<th colspan="2">{col}</th>'
                html += '</tr>\n'
                # Second header row
                html += '<tr>'
                for _ in districts_list + ['Total']:
                    html += '<th>N</th><th>%</th>'
                html += '</tr>\n'
                # Data rows
                for row in rows:
                    is_total_row = str(row[0]).lower() == 'total'
                    html += '<tr>'
                    # Row label
                    if is_total_row:
                        html += f'<td style="font-weight:bold;background:{total_color}">{row[0]}</td>'
                    else:
                        html += f'<td style="font-weight:bold">{row[0]}</td>'
                    # Row values
                    for i, val in enumerate(row[1:]):
                        is_total_col = (i // 2 == len(districts_list))
                        cell_style = ''
                        if is_total_row or is_total_col:
                            cell_style = f'font-weight:bold;background:{total_color}'
                        html += f'<td style="{cell_style}">{val}</td>'
                    html += '</tr>\n'
                html += '</table>'
                return html

            st.markdown(render_n_pct_table(columns_table, final_rows, main_question), unsafe_allow_html=True)

            # Download as CSV
            import csv
            import io
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            # First header row
            header_row1 = [main_question]
            for col in districts_list + ['Total']:
                header_row1.extend([col, ''])
            writer.writerow(header_row1)
            # Second header row
            header_row2 = [''] + [item for _ in districts_list + ['Total'] for item in ('N', '%')]
            writer.writerow(header_row2)
            # Data rows
            for row in final_rows:
                writer.writerow(row)
            csv_data = csv_buffer.getvalue().encode('utf-8')
            st.download_button(
                label="Download table as CSV",
                data=csv_data,
                file_name=f"{main_question}_table.csv",
                mime="text/csv"
            )
        else:
            st.info("No data available for this multi-selection variable.")

st.markdown("---")
st.caption(f"Charts are dynamically updated based on your selected District(s): {district_display}")
