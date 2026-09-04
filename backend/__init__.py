"""Puente de compatibilidad — se borra en la próxima versión.

El paquete pasó a llamarse `plotspace`. Este directorio existe por UN motivo
concreto y temporal: el server que está corriendo AHORA tiene en memoria el
comando `uvicorn backend.main:app`, y al aplicar la actualización re-ejecuta
con ESE comando. Si el módulo no existiera, uvicorn no levantaría y el server
no volvería — y el canary no lo atraparía, porque el canary importa el módulo
NUEVO (que está bien) y el fallo ocurre después, en el re-exec.

Una vez que la actualización pasó, el proceso nuevo ya usa `plotspace.main:app`
y esto no lo necesita nadie. Se borra entonces.
"""
