# Extraction quality report

## Ley N.° 32069, Ley General de Contrataciones Públicas

- Version: Texto con modificaciones posteriores hasta el 19-07-2026 · file `ley_32069_hasta_2026-07-19.pdf`
- Pages: 63 · kept: 63 · discarded: 0 
- Characters: 220,096 raw → 215,353 clean
- R1 gazette headers removed: 0 pages (0 chars)
- R2 text of another norm dropped: 0 chars

Sample from the middle of the document (page 32):

```text
Artículo 66. Adelantos

66.1. La entidad contratante puede entregar adelantos al contratista con la finalidad de otorgarle financiamiento o liquidez para la ejecución del contrato en las condiciones establecidas y fundamentadas en la estrategia de contratación.

66.2. El adelanto puede ser:

a) Directo.
b) Para materiales e insumos, equipamiento y mobiliario.
c) Otros que sean establecidos en el reglamento.

66.3. Los documentos del procedimiento de selección pueden establecer adelantos directos al contratista, los que en ningún caso exceden en conjunto del 30 % del monto del contrato original.

66.4. El reglamento establece las condiciones y demás criterios para otorgar los adelantos y para
```

## Decreto Supremo N.° 001-2026-EF, que modifica el Reglamento de la Ley N.° 32069

- Version: Publicado el 2026-01-08 · file `ds_001_2026_ef.pdf`
- Pages: 16 · kept: 16 · discarded: 0 
- Characters: 112,477 raw → 103,499 clean
- R1 gazette headers removed: 16 pages (912 chars)
- R2 text of another norm dropped: 6,270 chars

Sample from the middle of the document (page 9):

```text
“Artículo 194. Prestaciones adicionales de obra bajo el sistema de entrega solo construcción
(…)
194.3. No corresponde suscribir una adenda al contrato por la aprobación de la prestación adicional, bastando con su publicación en la Pladicop para que surta todos sus efectos. Se encuentra prohibida la aprobación de prestaciones adicionales en vía de regularización.
(…)”
“Artículo 195. Prestaciones adicionales de obra bajo el sistema de entrega diseño y construcción
(…)
195.2. La aprobación de las prestaciones adicionales en el componente de diseño se realiza conforme al numeral 193.1 del artículo 193.
(…)
195.4. No corresponde suscribir una adenda al contrato por la aprobación del adicional, b
```

## Before and after cleaning (DS 001-2026-EF)

Page 1, raw (header glued to the body, one PDF line per column line):

```text
33NORMAS LEGALESJueves 8 de enero de 2026 El Peruano / 
ECONOMÍA Y FINANZAS
Decreto Supremo que modifica el 
Reglamento de la Ley N° 32069, Ley General 
de Contrataciones Públicas, aprobado 
mediante Decreto Supremo N° 009-2025-
EF
DECRETO SUPREMO
Nº 001-2026-EF
EL PRESIDENTE DE LA REPÚBLICA
CONSIDERANDO:
Que, el Decreto Legislativo Nº 1439, Decreto 
Legislativo del Sistema Nacional de Abastecimiento, 
desarrolla dic
```

Page 1, clean (R1 header removed and kept as `pagina_diario = 33`, R3 lines joined into paragraphs):

```text
ECONOMÍA Y FINANZAS Decreto Supremo que modifica el Reglamento de la Ley N° 32069, Ley General de Contrataciones Públicas, aprobado mediante Decreto Supremo N° 009-2025-EF
DECRETO SUPREMO Nº 001-2026-EF
EL PRESIDENTE DE LA REPÚBLICA CONSIDERANDO:
Que, el Decreto Legislativo Nº 1439, Decreto Legislativo del Sistema Nacional de Abastecimiento, desarrolla dicho Sistema con la finalidad de establecer sus principios, defi
```

Page 16, raw end (another norm starts after the code `2474920-3`):

```text
pública
DENISSE AZUCENA MIRALLES MIRALLES
Ministra de Economía y Finanzas
2474920-3
Fijan índices de corrección monetaria para 
efectos de determinar el costo computable 
de los inmuebles enajenados por personas 
naturales, sucesiones indivisas o sociedades 
conyugales que optaron por tributar como 
tales
RESOLUCIÓN VICEMINISTERIAL
Nº 001-2026-EF/15.01
Lima, 6 de enero de 2026
CONSIDERANDO:
Que, mediante el artículo 
```

Page 16, clean (R2 cut at the code):

```text
Dado en la Casa de Gobierno, en Lima, a los siete días del mes de enero del año dos mil veintiséis.
JOSÉ ENRIQUE JERÍ ORÉ Presidente de la República
DENISSE AZUCENA MIRALLES MIRALLES Ministra de Economía y Finanzas
```
