# -*- coding: utf-8 -*-
"""PopovMV_FinalProject.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1eV6Kf7l3lDzGW1nV4fQATCLAGXBvDBOi

#Подготовка

## Импотры и инсталяции необходимых модулей
"""

#Подключим Google диск
from google.colab import drive
drive.mount('/content/drive')
!cp -r ./drive/My\ Drive/FinalProject/* .

!pip install -q catboost shap

!pip install -q gpx-cmd-tools

!pip install -q python-tcxparser

#!pip install -q pandas-profiling==3.1.0

!sudo apt install -q pv

import catboost as ctb
from catboost import Pool, cv
from google.colab import output
from pandas_profiling import ProfileReport
from feature_selector import FeatureSelector
import numpy as np
import pandas as pd
import seaborn as sns
import shap
import os
import gzip
import gc
import folium
import zipfile
from matplotlib import pyplot 
import matplotlib
from sklearn.model_selection import train_test_split
from sklearn import metrics
from sklearn.inspection import permutation_importance
from sklearn import preprocessing
import matplotlib.pyplot as plt

"""## Загрузка данных"""

#Разархивируем
!unzip all_data.zip | pv -l >/dev/null
!unzip activities.zip | pv -l >/dev/null

#Загрузим и соберем в один дата-сет
a_act = pd.read_csv('1_act.csv')
b_act = pd.read_csv('2_act.csv')
c_act = pd.read_csv('3_act.csv')
d_act = pd.read_csv('4_act.csv')
e_act = pd.read_csv('5_act.csv')
#У части спортсменов вес не был в данных, добавим руками
a_act['Athlete Weight'] = 90
b_act['Athlete Weight'] = 80
c_act['Athlete Weight'] = 85
allDf = pd.concat([a_act, b_act, c_act, d_act, e_act])

#Выделим отдельно датасет для Визуализации
# allDf_visual = allDf[['Activity ID', 'Filename']].copy()

"""## Первичный анализ (Draft) можно пропустить"""

#Инфа по всем столбцам
allDf.info()

profile = allDf.profile_report()
profile.to_file(output_file="Pandas Profiling Report — Strava.html")

#Не одно ли и то же?
allDf[['Commute','Activity Type']].loc[allDf['Commute'] == True] 
allDf[['Relative Effort','Relative Effort.1']]

#Два столбца с расстоянием, один в КМ, второс Метрах - оставим последний, более информативный
allDf[['Distance','Distancet.1']]

# Распределение по видам активности
RenameActType(a_act)
a_act['Activity Type'].value_counts()

allDf['Activity Gear'].describe()

allDf['Activity Gear'].value_counts()

allDf['Athlete Weight'].value_counts()

allDf['Activity Gear'].loc[allDf['Activity Gear'].isnull()] = 'Some Gear'

allDf[['Commute','Commute.1']]

"""## Чистим данные

###Подготовка:
*   Признаки "*Activity Name*" и "*Activity Description*" описательные и заполняются самим пользователем и не несут смысловой нагрузки для анализа - удаляем
*   Признаки "*Distance*" и "*Distance.1*" один в км, второй метрах - оставим последний, более информативный
*   "*Activity Date*","*Activity ID*" - Первый таймСтамп - нам не нужен, второй - просто ID тренировки - удаляем
*  "*Commute.1*","*Commute*","*From Upload*" - технологические признаки связаные с загрузкой данных - не нужны
*   "*Filename*" - ссылка на доп файлы - не нужен
*   "*Activity Gear*" - тип спорт.оборудовния - описание, слишком очевидно для разделения по видам Активности
"""

#Объявим нужны функции и константы (признаки и типы активностей) для Baseline

#Функция мапинга английских и русских названий активностей
def RenameActType(df):
  df.loc[(df['Activity Type']=='Бег'), 'Activity Type'] = 'Run'
  df.loc[(df['Activity Type']=='Лыжи'), 'Activity Type'] = 'Nordic Ski'
  df.loc[(df['Activity Type']=='Велосипед'), 'Activity Type'] = 'Ride'
  df.loc[(df['Activity Type']=='Плавание'), 'Activity Type'] = 'Swim'
  df.loc[(df['Activity Type']=='Ходьба'), 'Activity Type'] = 'Walk'
  df.loc[(df['Activity Type']=='Роликовые коньки'), 'Activity Type'] = 'Inline Skate'
  df.loc[(df['Activity Type']=='Коньки'), 'Activity Type'] = 'Ice Skate'
  df.loc[(df['Activity Type']=='Горные лыжи'), 'Activity Type'] = 'Alpine Ski'

def DropNanColumns(df,col_to_drop):
  df.drop(col_to_drop,1,inplace = True)

top_activity = ['Run', 'Ride', 'Nordic Ski','Roller Ski','Walk','Inline Skate','Workout'] #ТОП-7 активностям, по колличеству записей
col_to_drop_m = ['Activity Name','Activity Description','Activity Date','Distance', 'Activity ID','Filename', 'From Upload', 'Commute', 'Commute.1'] #Уберем сразу часть признаков

"""### Baseline"""

#Функция чистки
def CleanDataToLearning(allDf, col_to_drop_m = [], top_activity = []):
  RenameActType(allDf)
  col_to_drop = []
  allDf = allDf.loc[allDf['Activity Type'].isin(top_activity)]
  #col_to_drop = [feature for feature in allDf.columns if (allDf[feature].isnull().sum()/allDf[feature].size) >= 0.4] #Удаляем признаки, которые больше чем на 40% незаполнены
  col_to_drop += col_to_drop_m
  DropNanColumns(allDf,col_to_drop)
  return allDf

def CutX_Y(df):
  X = allDf.copy()
  y = X['Activity Type']
  X.drop(['Activity Type'],1,inplace = True)
  return X, y

def FeatureOptimaiser(df, col_to_drop_m, top_activity, correlation_threshold, missing_threshold, plotHMap):
  df = CleanDataToLearning(df, col_to_drop_m, top_activity)
  X_1, y_1  = CutX_Y(df)
  fs = FeatureSelector(data = X_1, labels = y_1)
  fs.identify_collinear(correlation_threshold)
  fs.identify_missing(missing_threshold)
  fs.identify_single_unique()
  if plotHMap:
    fs.plot_collinear()
  return fs.ops['collinear'], fs.ops['missing'], fs.ops['single_unique']

# список признаков для удаления
collinear_features, missing_features, single_features = FeatureOptimaiser(allDf, col_to_drop_m, top_activity, 0.49, 0.6, False)

fig = plt.figure(figsize=(8,8), dpi = 200)
corr_matrix = allDf.corr()
sns.heatmap(corr_matrix, annot=True, fmt=".2g", cmap="Oranges")

plt.savefig("corr_mtx.png", format = 'png', dpi=200)

"""# Разделение датасета, Подготовка моделей и Обучение

## Разделение датасета на Трениновочную, Валидационную и Тестовые Выборки

###Вариант 1 (выделяем Тестовую, тренировочную и валидационную выборки из всего датасета)
"""

allDf = CleanDataToLearning(allDf, col_to_drop_m+collinear_features+missing_features+single_features, top_activity)

X, y  = CutX_Y(allDf)
categorical_feature = [feature for feature in X.columns if X[feature].dtypes == "object"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20) # выделим тестовую
X_train, X_val, y_train, y_val = train_test_split(X_train, y_train, test_size=0.20) # разделм на тренировочную и валидационную

"""###Вариант 2 (выделяем Тестовую из данных одного спортсмена, а тренировочные и валидационные выборки из всех остальных)"""

#Все кроме данных одного спортмена
allDf = pd.concat([a_act, e_act, b_act, c_act])
allDf = CleanDataToLearning(allDf, col_to_drop_m+collinear_features+missing_features+single_features, top_activity)
X_train, y_train = CutX_Y(allDf)

#Данные одного на тест
d_act = CleanDataToLearning(d_act, col_to_drop_m+collinear_features+missing_features+single_features, top_activity)
X_test, y_test = CutX_Y(d_act)

X_train, X_val, y_train, y_val = train_test_split(X_train, y_train, test_size=0.20) # разделм на тренировочную и валидационную

"""## Модели"""

def ModelCatBoostClass(X_train, X_val, y_train, y_val, cat_features):
  train_dataset = Pool(data=X_train,
                     label=y_train,
                     cat_features=cat_features)

  eval_dataset = Pool(data=X_val,
                    label=y_val,
                    cat_features=cat_features)

  model_CBC = ctb.CatBoostClassifier(iterations=100,
                           learning_rate=1,
                           depth=4,
                           loss_function='MultiClass')
  model_CBC.fit(X_train, y_train)
  return model_CBC

"""## Обучение"""

#Обучение модели
modelCBS = ModelCatBoostClass(X_train, X_val, y_train, y_val, categorical_feature)

"""##Метрики"""

#Метрики
expected_y  = y_test
predicted_y = modelCBS.predict(X_test)
print(metrics.classification_report(expected_y, predicted_y))
print(metrics.confusion_matrix(expected_y, predicted_y))

y_to_lab = expected_y.unique()
y_to_lab.sort(axis=0)
fig = plt.figure(figsize=(8,8), dpi = 200)
matplotlib.rc('xtick', labelsize=20) 
matplotlib.rc('ytick', labelsize=20) 
sns.heatmap(metrics.confusion_matrix(y_test, modelCBS.predict(X_test)), annot=True, fmt="d", cmap="Greens", xticklabels=y_to_lab, yticklabels =y_to_lab)
plt.ylabel("Real value")
plt.xlabel("Predicted value")

plt.savefig("con_mtx.png", format = 'png', dpi=200)

"""# Визуализация - не актуально - решил отказаться - не имеет отношения к анализу"""

allDf_visual

def unpack_gz(in_file_name):
  gzip_file = gzip.GzipFile(in_file_name, 'rb')
  data = gzip_file.read()
  return data.decode('utf-8')

gpx_file_1= unpack_gz('./activities/227157048.gpx.gz')
gpx_file_2= unpack_gz('./activities/227150014.gpx.gz')

tcx_file_1= unpack_gz('./activities/325708135.tcx.gz')

import tcxparser
tcx = tcxparser.TCXParser(tcx_file_1)

import gpxpy
import gpxpy.gpx

def process_gpx_to_df(file_content):
  gpx = gpxpy.parse(file_content) 
 
  track = gpx.tracks[0]
  segment = track.segments[0]
  data = []
  segment_length = segment.length_3d()
  for point_idx, point in enumerate(segment.points):
    data.append([point.longitude, point.latitude,point.elevation,point.time, segment.get_speed(point_idx)])
    columns = ['Longitude', 'Latitude', 'Altitude', 'Time', 'Speed']
    gpx_df = pd.DataFrame(data, columns=columns)
 
  points = []
  for track in gpx.tracks:
    for segment in track.segments:
      for point in segment.points:
        points.append(tuple([point.latitude, point.longitude]))
  return gpx_df, points

df_to_plt_1, points_to_plt_1 = process_gpx_to_df(gpx_file_1)
df_to_plt_2, points_to_plt_2 = process_gpx_to_df(gpx_file_2)

df_to_plt_1

mymap = folium.Map( location=[ df_to_plt_1.Latitude.mean(), df_to_plt_1.Longitude.mean() ], zoom_start=10, tiles=None, width = '60%', height = '60%') #
folium.TileLayer('openstreetmap', name='OpenStreet Map').add_to(mymap)

folium.PolyLine(points_to_plt_2, color='red', weight=4.5, opacity=.5).add_to(mymap)
folium.PolyLine(points_to_plt_1, color='blue', weight=4.5, opacity=.5).add_to(mymap)

folium.Circle(location=[ df_to_plt_1.Latitude.mean(), df_to_plt_1.Longitude.mean()], radius = 1000, color = 'blue', fill = True, fill_opacity = 0.8, popup='Nordic Ski').add_to(mymap)
folium.Circle(location=[ df_to_plt_2.Latitude.mean(), df_to_plt_2.Longitude.mean()], radius = 1000, color = 'red', fill = True, fill_opacity = 0.8, popup='Some Act').add_to(mymap)

mymap.png_enabled = False

mymap