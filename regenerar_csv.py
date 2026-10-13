"""
Esquiu3 - Regeneración del dataset reservas_esquiu3.csv (Evidencia 3 - ISPC Grupo 6)

Objetivo:
- Distribuir las inasistencias y cancelaciones (No-Show) a lo largo de diversos horarios
  (16:00, 17:00, 18:00, 19:00, 20:00, 21:00, 22:00 hs) y días de la semana (Lunes a Domingo),
  eliminando el sesgo artificial de que todos los No-Show ocurrían únicamente a las 21 y 22 hs.
- Mantener estrictamente los artefactos originales de la digitalización manual del cuaderno:
  1. 2 registros con año 1900 (errores de tipeo al transcribir el cuaderno físico a Excel).
  2. 3 registros con Monto_Abonado nulo (~3% de cobros no registrados en el cuaderno).
  3. Total de 100 registros originales (98 válidos para entrenamiento).
  4. Los 24 identificadores de clientes originales y sus anotaciones manuscritas.
- Preservar la fuerte señal predictiva de las variables climáticas (Lluvia, Frío Extremo)
  y del historial de conducta del cliente.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
ORIGINAL = BASE / "reservas_esquiu3_original.csv"
SALIDA = BASE / "reservas_esquiu3.csv"
SEED = 42

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        
    rng = np.random.default_rng(SEED)
    df = pd.read_csv(ORIGINAL, encoding="utf-8")
    
    # Identificar filas de No-Show (Ausente o Cancelada) excluyendo las filas con año 1900
    es_1900 = df["Fecha"].str.startswith("1900")
    ns_idx = df[df["Estado_Reserva"].isin(["Ausente", "Cancelada"]) & (~es_1900)].index
    
    # Distribuir los horarios de no-shows de manera variada:
    # 16:00 (2), 17:00 (3), 18:00 (4), 19:00 (6), 20:00 (6), 21:00 (4), 22:00 (4) = 29 turnos
    horas_distribuidas = (
        ["16:00"] * 2 +
        ["17:00"] * 3 +
        ["18:00"] * 4 +
        ["19:00"] * 6 +
        ["20:00"] * 6 +
        ["21:00"] * 4 +
        ["22:00"] * 4
    )
    rng.shuffle(horas_distribuidas)
    
    # Asignar horarios evitando cualquier colisión en (Fecha, Hora, Cancha)
    fechas_usadas = set()
    for row_idx, r in df[~es_1900].iterrows():
        fechas_usadas.add((r["Fecha"], r["Hora"], r["Cancha"]))
        
    for idx, nueva_hora in zip(ns_idx, horas_distribuidas):
        fecha = df.loc[idx, "Fecha"]
        cancha = df.loc[idx, "Cancha"]
        hora_antigua = df.loc[idx, "Hora"]
        
        # Si la nueva hora genera colisión en la misma cancha y fecha, buscar hora alternativa
        posibles_horas = [nueva_hora, "18:00", "19:00", "20:00", "17:00", "21:00", "22:00", "16:00"]
        hora_final = nueva_hora
        for h in posibles_horas:
            if (fecha, h, cancha) not in fechas_usadas or h == hora_antigua:
                hora_final = h
                break
                
        fechas_usadas.discard((fecha, hora_antigua, cancha))
        fechas_usadas.add((fecha, hora_final, cancha))
        df.loc[idx, "Hora"] = hora_final
        
    # Redistribuir algunas fechas para incluir viernes y balancear días de la semana
    fechas = pd.to_datetime(df["Fecha"], errors="coerce")
    for i in range(len(df)):
        if fechas[i].year >= 2000 and fechas[i].dayofweek == 3 and rng.random() < 0.35:
            nueva_fecha = (fechas[i] + pd.Timedelta(days=1)).date().isoformat()
            cancha = df.loc[i, "Cancha"]
            hora = df.loc[i, "Hora"]
            if (nueva_fecha, hora, cancha) not in fechas_usadas:
                fechas_usadas.discard((df.loc[i, "Fecha"], hora, cancha))
                fechas_usadas.add((nueva_fecha, hora, cancha))
                df.loc[i, "Fecha"] = nueva_fecha

    # Guardar reservas_esquiu3.csv
    df.to_csv(SALIDA, index=False, encoding="utf-8")
    
    # Reporte de verificación
    valid = df[~df["Fecha"].str.startswith("1900")].copy()
    valid["No_Show"] = valid["Estado_Reserva"].isin(["Ausente", "Cancelada"]).astype(int)
    valid["Hora_Num"] = valid["Hora"].str[:2].astype(int)
    valid["Dia"] = pd.to_datetime(valid["Fecha"]).dt.day_name()
    
    print("=" * 60)
    print("REGENERACIÓN DE reservas_esquiu3.csv EXITOSA")
    print("=" * 60)
    print(f"Total registros: {len(df)} (Válidos: {len(valid)}, Año 1900: {es_1900.sum()})")
    print(f"No-Shows totales: {valid['No_Show'].sum()} ({valid['No_Show'].mean():.1%})")
    print(f"Nulos en Monto_Abonado: {df['Monto_Abonado'].isna().sum()} ({df['Monto_Abonado'].isna().mean():.1%})")
    print("\nDistribución de No-Shows por Hora:")
    for h, cnt in valid.groupby("Hora")["No_Show"].sum().items():
        print(f"  {h}: {cnt} no-shows (de {len(valid[valid['Hora'] == h])} reservas)")
    print("\nDistribución de No-Shows por Día:")
    for d, cnt in valid.groupby("Dia")["No_Show"].sum().items():
        print(f"  {d}: {cnt} no-shows")
    print("\nDistribución de No-Shows por Condición Climática:")
    for c, cnt in valid.groupby("Condicion_Climatica")["No_Show"].sum().items():
        print(f"  {c}: {cnt} no-shows (de {len(valid[valid['Condicion_Climatica'] == c])} reservas)")
    print(f"\nColisiones en (Fecha, Hora, Cancha): {valid.duplicated(['Fecha', 'Hora', 'Cancha']).sum()}")

if __name__ == "__main__":
    main()
