import pandas as pd
import altair as alt
import streamlit as st
import folium
from streamlit_folium import st_folium
import numpy as np
import pickle
from streamlit_js_eval import streamlit_js_eval

st.set_page_config(page_title="NYC Biking Data", layout="wide")
st.title("Bike ridership in NYC")

### filter dfs func
def filter_df_counters(df, counter_selection):
    new_df = df[df.index.get_level_values('id').isin(counter_selection)].copy()
    return new_df

def filter_df_dates(df, start_date, end_date):
    date_idx = df.index.get_level_values('date')
    criteria = (date_idx >= start_date) & (date_idx<=end_date)
    new_df = df.loc[criteria].copy()
    return new_df

# read files
with open('data/retrieval_date.pkl', 'rb') as f:
    retrieval_date = pickle.load(f)

hr = pd.read_pickle('data/streamlit_by_hr.pkl')
wk = pd.read_pickle('data/streamlit_by_wk.pkl')
hist_wk = pd.read_pickle('data/streamlit_hist_by_wk.pkl')
counters = pd.read_pickle('data/streamlit_counters.pkl')
count_per_wk = hr.reset_index()[['id', 'counts']].groupby('id').sum()

all_counters = np.sort(list(counters['name'].unique()))

# set chart widths
browser_width = streamlit_js_eval(js_expressions='window.innerWidth', key='SCR')
legend_width = browser_width * 0.05
chart_width = browser_width * 0.65

### SIDEBAR
with st.sidebar:
    selected_counters = st.multiselect("select counters:", 
                                options=all_counters,
                                default=['Brooklyn Br',
                                         'Manhattan Br',
                                         'Williamsburg Br']

                                )
    if len(selected_counters)==0:
        selected_counter_ids = counters.index.to_list()
        selected_counters = all_counters
    else:
        selected_counter_ids = counters.loc[counters['name'].isin(selected_counters), :].index

    ### DATE SLIDER
    st.write('')
    select_hist_wk = filter_df_counters(hist_wk, selected_counter_ids)
    date_list = pd.to_datetime(select_hist_wk.index.get_level_values('date').to_series().dt.strftime('%Y-%m').unique()).to_series()

    selected_dates = st.select_slider("select historical chart dates:",
                                    value=[date_list[0], date_list[-1]],
                                    options=date_list,
                                    format_func=lambda date_list: date_list.strftime('%b-%Y')
                                    ) 
    if len(selected_dates)==0:
        selected_dates = (date_list[0], date_list[-1])
    start_date = selected_dates[0]
    end_date = selected_dates[1]

    ### MAP
    select_counters = filter_df_counters(counters, selected_counter_ids)
    m = folium.Map(location=[40.720, -73.94], zoom_start=11)
    folium.TileLayer('cartodbdark_matter').add_to(m)

    for i, c in select_counters.iterrows():
        # establish params
        lat = c['latitude']
        long = c['longitude']
        name = c['name']
        id = i
        count = count_per_wk.loc[id]
        color = c['color']

        # create tooltip
        tooltip_content = f"""
        <p style="font-family: monospace;"><strong>{name}<br>
        {int(np.round(count[0],0))}</strong> daily riders</p>
    """
        # create markers
        circle = folium.CircleMarker(
            location=(lat,long),
            tooltip=folium.Tooltip(tooltip_content),
            radius=count[0] * 0.005,
            color=color,
            fill=True,
            fill_color=color,
            highlight=True
        ).add_to(m)

    st_folium(m, width=400, height=400)

### filter dfs
select_hr = filter_df_counters(hr, selected_counter_ids)
select_wk = filter_df_counters(wk, selected_counter_ids)
select_hist_wk = filter_df_dates(select_hist_wk, start_date, end_date)

## LEGEND
num_selected_counters = len(selected_counters)
selected_counter_mapping = counters.loc[selected_counter_ids]
selected_counter_mapping['count'] = 1

hover_selection = alt.selection_point(on='mouseover', fields=['name'], nearest=True)

legend_chart = alt.Chart(selected_counter_mapping).mark_bar().encode(
    y=alt.Y('name:O', axis=alt.Axis(title=None, labelLimit=300), scale=alt.Scale(padding=0.1)),
    x=alt.X('count:Q', axis=alt.Axis(title=None, labels=False)), 
    color=alt.Color('color:N', scale=None, legend=None),
    tooltip=alt.value(None),
    opacity=alt.condition(hover_selection, alt.value(1), alt.value(0.4))
    ).properties(width=legend_width).add_params(hover_selection)


### HOURLY LINE CHART
hr_chart = alt.Chart(select_hr.reset_index()).mark_line().encode(
    x=alt.X('utchoursminutes(display_time):T', axis=alt.Axis(title=None, format='%-I %p', grid=True)),
    y=alt.Y('counts:Q', title='riders per hour'),
    color=alt.Color('color:N', scale=None),
    opacity=alt.condition(hover_selection, alt.value(1), alt.value(0.4))
    ).properties(title='average hourly ridership', width=chart_width).add_params(hover_selection)

# Create a selection that chooses the nearest point & selects based on x-value
nearest_hr = alt.selection_point(nearest=True, on='mouseover',
                        fields=['display_time'], empty=False)

# Transparent selectors across the chart. This is what tells us
# the x-value of the cursor
selectors = alt.Chart(select_hr.reset_index()).mark_point().encode(
    x='utchoursminutes(display_time):T',
    opacity=alt.value(0),
    tooltip=alt.value(None)
).add_params(
    nearest_hr
)

# Draw points on the line, and highlight based on selection
points = hr_chart.mark_point().encode(
    opacity=alt.condition(nearest_hr, alt.value(1), alt.value(0))
)

# Draw text labels near the points, and highlight based on selection
text = hr_chart.mark_text(align='left', dx=10, dy=10).encode(
    text=alt.condition(nearest_hr, alt.Text('counts:Q', format='.0f'), alt.value(' '))
)

# Draw a rule at the location of the selection
rules = alt.Chart(select_hr.reset_index()).mark_rule(color='gray').encode(
    x='utchoursminutes(display_time):T'
).transform_filter(
    nearest_hr
)

# Put the five layers into a chart and bind the data
hr_chart_bound = alt.layer(
    hr_chart, selectors, points, rules, text
)

### WEEKLY LINE CHART
wk_chart = alt.Chart(select_wk.reset_index()).mark_line().encode(
    x=alt.X('display_date:T', axis=alt.Axis(tickCount={"interval": "month", "step": 1}, tickExtra=True, grid=True), title=None),
    y=alt.Y('counts:Q', title='riders per week'),
    color=alt.Color('color:N', scale=None),
    tooltip=['name:O', 'counts:Q', 'display_date:T'],
    opacity=alt.condition(hover_selection, alt.value(1), alt.value(0.4))
    ).properties(title='average weekly ridership', width=chart_width).add_params(hover_selection)

# Create a selection that chooses the nearest point & selects based on x-value
nearest_wk = alt.selection_point(nearest=True, on='mouseover',
                        fields=['display_date'], empty=False)

# Transparent selectors across the chart. This is what tells us
# the x-value of the cursor
selectors = alt.Chart(select_wk.reset_index()).mark_point().encode(
    x='display_date:T',
    opacity=alt.value(0),
    tooltip=alt.value(None)
).add_params(
    nearest_wk
)

# Draw points on the line, and highlight based on selection
points = wk_chart.mark_point().encode(
    opacity=alt.condition(nearest_wk, alt.value(1), alt.value(0))
)

# Draw text labels near the points, and highlight based on selection
text = wk_chart.mark_text(align='left', dx=10, dy=10).encode(
    text=alt.condition(nearest_wk, alt.Text('counts:Q', format=',.0f'), alt.value(' '))
)

# Draw a rule at the location of the selection
rules = alt.Chart(select_wk.reset_index()).mark_rule(color='gray').encode(
    x='display_date:T'
).transform_filter(
    nearest_wk
)

# Put the five layers into a chart and bind the data
wk_chart_bound = alt.layer(
    wk_chart, selectors, points, rules, text
)

### HISTORICAL WEEKLY CHART
hist_wk_chart = alt.Chart(select_hist_wk.reset_index()).mark_line().encode(
    x=alt.X('date:T', axis=alt.Axis(tickCount={'interval':'month', 'step':3}, title=None, format='%b-%Y', grid=True)),
    y=alt.Y('counts:Q', title='riders per week'),
    color=alt.Color('color:N', scale=None),
    tooltip='name:O',
    opacity=alt.condition(hover_selection, alt.value(1), alt.value(0.4))
    ).properties(title='historical weekly ridership', width=chart_width).add_params(hover_selection)


# render
combo_chart = hr_chart_bound & wk_chart_bound & hist_wk_chart
combo_chart_legend = legend_chart | combo_chart
st.altair_chart(combo_chart_legend.configure_axis(labelFontSize=16).configure_title(fontSize=24), use_container_width=True)