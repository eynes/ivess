T15709. Agrega el concepto de "grupo de empresas" (`res.company.group`) al selector de
compañías: al elegir un grupo se activan todas sus empresas reales, como si se tildaran
a mano. El grupo es solo un objeto de conveniencia de interfaz y contexto, no una
sociedad: no altera la contabilidad ni la configuración fiscal.

Permite además bloquear por usuario el cambio de empresa/grupo (`can_switch_company`).
El bloqueo se fuerza del lado servidor: para un usuario bloqueado se descartan del
contexto (`allowed_company_ids`) las empresas fuera de su alcance, de modo que manipular
la cookie `cids` o el contexto no tiene efecto, tampoco en código que lee la clave
directo del contexto. Código de servidor que necesite una empresa fuera del alcance debe
usar `sudo()` antes de cambiarla (`with_company` dentro del grupo funciona normal).
