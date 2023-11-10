# Automated System for Determining Atmospheric Stability (AeroWatch) #
## By Wahyu Kurniawan ##
### Indonesia Agency for Meteorology, Climatology, and Geophysics (BMKG) ###
### Centre for Aeronautical Meteorology - Subdivision for Aeronautical Meteorology Information Services ###


## Preparation - Import Module ##
import streamlit as st
import folium
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import metpy.calc as mpcalc
from metpy.units import units, pandas_dataframe_to_unit_arrays
from siphon.simplewebservice.wyoming import WyomingUpperAir

## Threshold Criteria for Categorization of Atmospheric Stability ##
def index_criteria(cape_value, k_index_value, lifted_index_value, showalter_index_value):
    if cape_value > 2500 and k_index_value > 30 and lifted_index_value < -5:
        kategori = "Labil Kuat"
    elif cape_value > 1000 and k_index_value > 20 and lifted_index_value < -3:
        kategori = "Labil Sedang"
    elif cape_value > 100 and k_index_value > 0 and showalter_index_value < 0:
        kategori = "Labil Lemah"
    else:
        kategori = "Stabil"
    return kategori

def get_magnitude(quantity):
    return quantity.magnitude

def retrieve_data_from_wyoming(date, stations):
    data_per_station = {}
    for station in stations:
        try: # error handling
            dfori = WyomingUpperAir.request_data(date, station)
            data_per_station[station] = dfori
        except requests.exceptions.HTTPError as e:
            st.write(f'Oops, it looks like the server is busy. Hold on. Retrying to retrieve data ...')
        except ValueError:
            st.write(f'No data available for {date}, for station {station}')
    return data_per_station

def calculate_stability(data_per_station, station_to_location):
    dfstationdata = pd.concat(data_per_station.values()).drop_duplicates(['station'])
    dfindex = pd.DataFrame(columns=['Waktu','Lintang','Bujur','CAPE', 'K-Index', 'Lifted Index', 'Showalter Index'], index=station_to_location.items())
    for key, value in data_per_station.items(): # loop thorugh dict
        df_units = value.units
        da = pandas_dataframe_to_unit_arrays(value, column_units=df_units)
        profile = mpcalc.parcel_profile(da['pressure'], da['temperature'][0], da['dewpoint'][0])
        time = dfstationdata[dfstationdata['station'] == key]['time'].values[0]
        lat = dfstationdata[dfstationdata['station'] == key]['latitude'].values[0]
        lon = dfstationdata[dfstationdata['station'] == key]['longitude'].values[0]
        cape, cin = mpcalc.cape_cin(da['pressure'], da['temperature'], da['dewpoint'], profile)
        cape = round(cape.magnitude, 0)
        kindex = mpcalc.k_index(da['pressure'], da['temperature'], da['dewpoint'])
        kindex = round(kindex.magnitude, 0)
        lift_index = mpcalc.lifted_index(da['pressure'], da['temperature'], profile)
        lift_index = np.round(lift_index.magnitude, 1)
        showalter = mpcalc.showalter_index(da['pressure'], da['temperature'], da['dewpoint'])
        showalter = np.round(showalter.magnitude, 1)
        # assign to new dataframe
        dfindex.loc[key] = [time, lat, lon, cape, kindex, lift_index, showalter]
    dfindexnew = dfindex.copy()
    for i in dfindex.columns: # loop sebanyak kolom dfindex
        try: # error handling untuk mencegah error akibat kolom tdk ada unitnya
            dfindexnew[i] = dfindex[i].apply(get_magnitude)
        except AttributeError:
            pass
    dfindexnew['Kategori'] = np.nan
    dfindexnew['Kategori'] = dfindexnew.apply(lambda row: index_criteria(row['CAPE'], row['K-Index'], row['Lifted Index'], row['Showalter Index']), axis=1)
    dfindexnew = dfindexnew.dropna(subset=['Lintang', 'Bujur'])    
    return dfindexnew

def add_legend(map):
    legend_html = """
    <div style="position: fixed; bottom: 50px; left: 50px; background-color: rgba(255, 255, 255, 0.8); border-radius: 5px; z-index: 1000; padding: 10px; font-size: 12px;">
        <div style="background-color: green; width: 10px; height: 10px; display: inline-block;"></div> Stabil<br>
        <div style="background-color: yellow; width: 10px; height: 10px; display: inline-block;"></div> Labil Lemah<br>
        <div style="background-color: orange; width: 10px; height: 10px; display: inline-block;"></div> Labil Sedang<br>
        <div style="background-color: red; width: 10px; height: 10px; display: inline-block;"></div> Labil Kuat
    </div>
    """
    map.get_root().html.add_child(folium.Element(legend_html))

def mapplot(df):
    df = df.dropna(subset=['Lintang', 'Bujur'])
    # Create a base map
    m = folium.Map(location=[df['Lintang'].mean(), df['Bujur'].mean()], zoom_start=5)
    # Add points to the map
    for _, row in df.iterrows():
        if row['Kategori'] == 'Stabil':
            color = 'green'
        elif row['Kategori'] == 'Labil Lemah':
            color = 'yellow'
        elif row['Kategori'] == 'Labil Sedang':
            color = 'orange'
        elif row['Kategori'] == 'Labil Kuat':
            color = 'red'
        # Create a circle marker with a popup for location and category
        circle_marker = folium.CircleMarker(
            location=[row['Lintang'], row['Bujur']],
            radius=10,
            color=color,
            fill=True,
            fill_color=color
        )

        # Add a popup for category information (on click)
        category_popup = folium.Popup(f"{row.name[-1]}\n\n: {row['Kategori']}\n\nCAPE: {row['CAPE']}\n\nKI: {row['K-Index']}\n\nLI: {row['Lifted Index']}\n\nSI: {row['Showalter Index']}", parse_html=True)
        circle_marker.add_child(category_popup)
        
        # Add the circle marker to the map
        circle_marker.add_to(m)

    # Add legend to the map
    add_legend(m)

    return m


def main():
    # Streamlit UI
    st.title('Automated System for Determining Atmospheric Stability (ASDAS)')

    current_datetime_utc = datetime.utcnow()
    last_data_time_utc = current_datetime_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    if current_datetime_utc.hour >= 12:
        next_data_time_utc = last_data_time_utc + timedelta(hours=12)
    else:
        next_data_time_utc = last_data_time_utc
    date = datetime(2023, 10, 16, 00)

    # comment ini untuk percobaan biar ga lama runningnya kalo error
    stations = ['WITT','WIMM','WIMG','WIBB','WION','WIKK','WIPL','WIII','WIIL','WRSJ','WRRR','WRLR','WRBB','WRLL','WIOO',
                'WRBI','WAAA','WAML','WAMM','WRKC','WRKK','WAMT','WAPP','WAPI','WABB','WASS','WAJJ','WAJW','WAKK']
    station_to_location = {
        'WITT': 'Aceh',
        'WIMM': 'Medan',
        'WIMG': 'Padang',
        'WIBB': 'Pekanbaru',
        'WION': 'Ranai',
        'WIKK': 'Pangkal Pinang',
        'WIPL': 'Bengkulu',
        'WIII': 'Jakarta',
        'WIIL': 'Cilacap',
        'WRSJ': 'Surabaya',
        'WRRR': 'Denpasar',
        'WRLR': 'Tarakan',
        'WRBB': 'Banjarmasin',
        'WRLL': 'Balikpapan',
        'WIOO': 'Pontianak',
        'WRBI': 'Pangkalan Bun',
        'WAAA': 'Makassar',
        'WAML': 'Palu',
        'WAMM': 'Manado',
        'WRKC': 'Maumere',
        'WRKK': 'Kupang',
        'WAMT': 'Ternate',
        'WAPP': 'Ambon',
        'WAPI': 'Saumlaki',
        'WABB': 'Biak',
        'WASS': 'Sorong',
        'WAJJ': 'Jayapura',
        'WAJW': 'Wamena',
        'WAKK': 'Merauke'
        }

    on = st.checkbox('Start Data Processing')
    if on:
        st.write('Retrieving Latest Data from Wyoming ...')
        data_per_station = retrieve_data_from_wyoming(date, stations)
        st.write('Finish retrieving data from Wyoming')
        st.write('Calculating Atmospheric Stability Index')
        df = calculate_stability(data_per_station, station_to_location)
        st.write('Displaying Calculated Atmospheric Stability Index')
        st.dataframe(df)

    dmap = st.checkbox('Would like to displaying maps?')
    if dmap:
        st.write('Displaying maps')
        mapp = mapplot(df)
        folium_static(mapp)

if __name__ == "__main__":
    main()
