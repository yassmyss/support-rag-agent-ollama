# PostgreSQL

## La aplicación no conecta con PostgreSQL
1. Verificar que el host, puerto y nombre de base de datos configurados son correctos.
2. Comprobar que PostgreSQL está iniciado.
3. Verificar conectividad al puerto configurado.
4. Revisar logs de la aplicación y PostgreSQL buscando el error exacto.
5. Distinguir entre fallo de red, autenticación, permisos y base de datos inexistente.
6. Nunca mostrar ni registrar contraseñas en texto plano.
7. No modificar pg_hba.conf ni reglas de firewall sin autorización.

## Escalado
Escalar si requiere cambios de permisos, firewall, configuración del servidor o recuperación de datos.

