-- =====================================================================
-- ISO 27001 - Row Level Security (RLS) para Gestion y Distribucion
-- =====================================================================
-- Regla general: cada usuario ve solo la informacion de su propia
-- sucursal, EXCEPTO transferencias (de stock, de colaborador y por
-- lote), que tambien son visibles para la sede destino aunque no las
-- haya originado. El rol 'admin' (sucursal_usuaria.rol = 'admin') ve
-- y administra todo, sin restriccion.
--
-- IMPORTANTE: el backend de la app usa la service_role key, que por
-- diseno de Supabase IGNORA RLS por completo. Esto no cambia el
-- comportamiento actual de la aplicacion; es una capa de defensa
-- adicional para cualquier conexion futura que use una clave de menor
-- privilegio (anon/authenticated) en vez de service_role.
--
-- Como aplicar: Supabase Dashboard -> SQL Editor -> pegar todo -> Run.
-- Es seguro reejecutar (usa IF EXISTS / OR REPLACE donde corresponde).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Funciones auxiliares (SECURITY DEFINER: evitan recursion de RLS
--    al leer sucursal_usuaria para saber quien es el usuario actual)
-- ---------------------------------------------------------------------

create or replace function public.mi_id_suc()
returns integer
language sql
stable
security definer
set search_path = public
as $$
  select id_suc from public.sucursal_usuaria where id_usuario = auth.uid()
$$;

create or replace function public.soy_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.sucursal_usuaria
    where id_usuario = auth.uid() and rol = 'admin'
  )
$$;

-- ---------------------------------------------------------------------
-- 2. sucursal_usuaria: lectura abierta a cualquier autenticado
--    (se necesita para listados/nombres de otras sedes), escritura
--    solo admin.
-- ---------------------------------------------------------------------
alter table public.sucursal_usuaria enable row level security;

drop policy if exists sel_sucursal_usuaria on public.sucursal_usuaria;
create policy sel_sucursal_usuaria on public.sucursal_usuaria
  for select using (auth.uid() is not null);

drop policy if exists write_sucursal_usuaria on public.sucursal_usuaria;
create policy write_sucursal_usuaria on public.sucursal_usuaria
  for all using (soy_admin()) with check (soy_admin());

-- ---------------------------------------------------------------------
-- 3. producto_catalogo: catalogo compartido, lectura abierta,
--    escritura solo admin.
-- ---------------------------------------------------------------------
alter table public.producto_catalogo enable row level security;

drop policy if exists sel_producto_catalogo on public.producto_catalogo;
create policy sel_producto_catalogo on public.producto_catalogo
  for select using (auth.uid() is not null);

drop policy if exists write_producto_catalogo on public.producto_catalogo;
create policy write_producto_catalogo on public.producto_catalogo
  for all using (soy_admin()) with check (soy_admin());

-- ---------------------------------------------------------------------
-- 4. Tablas propias de una sola sucursal (id_sucursal directo)
-- ---------------------------------------------------------------------
alter table public.colaborador enable row level security;
drop policy if exists propia_sede_colaborador on public.colaborador;
create policy propia_sede_colaborador on public.colaborador
  for all using (id_sucursal = mi_id_suc() or soy_admin())
  with check (id_sucursal = mi_id_suc() or soy_admin());

alter table public.inventario_stock enable row level security;
drop policy if exists propia_sede_inventario on public.inventario_stock;
create policy propia_sede_inventario on public.inventario_stock
  for all using (id_sucursal = mi_id_suc() or soy_admin())
  with check (id_sucursal = mi_id_suc() or soy_admin());

alter table public.factura_ingreso enable row level security;
drop policy if exists propia_sede_factura on public.factura_ingreso;
create policy propia_sede_factura on public.factura_ingreso
  for all using (id_sucursal = mi_id_suc() or soy_admin())
  with check (id_sucursal = mi_id_suc() or soy_admin());

alter table public.entrega_insumo enable row level security;
drop policy if exists propia_sede_entrega on public.entrega_insumo;
create policy propia_sede_entrega on public.entrega_insumo
  for all using (id_sucursal = mi_id_suc() or soy_admin())
  with check (id_sucursal = mi_id_suc() or soy_admin());

alter table public.anulacion_factura_solicitud enable row level security;
drop policy if exists propia_sede_anulacion on public.anulacion_factura_solicitud;
create policy propia_sede_anulacion on public.anulacion_factura_solicitud
  for all using (id_sucursal = mi_id_suc() or soy_admin())
  with check (id_sucursal = mi_id_suc() or soy_admin());

alter table public.notificacion enable row level security;
drop policy if exists propia_sede_notificacion on public.notificacion;
create policy propia_sede_notificacion on public.notificacion
  for all using (id_sucursal = mi_id_suc() or soy_admin())
  with check (id_sucursal = mi_id_suc() or soy_admin());

alter table public.csv_generados enable row level security;
drop policy if exists propia_sede_csv on public.csv_generados;
create policy propia_sede_csv on public.csv_generados
  for all using (id_sucursal = mi_id_suc() or soy_admin())
  with check (id_sucursal = mi_id_suc() or soy_admin());

-- ---------------------------------------------------------------------
-- 5. Tablas "hijas" que heredan la sede a traves de una tabla padre
-- ---------------------------------------------------------------------
alter table public.detalle_factura enable row level security;
drop policy if exists propia_sede_detalle_factura on public.detalle_factura;
create policy propia_sede_detalle_factura on public.detalle_factura
  for all using (
    soy_admin() or exists (
      select 1 from public.factura_ingreso f
      where f.id_factura = detalle_factura.id_factura and f.id_sucursal = mi_id_suc()
    )
  )
  with check (
    soy_admin() or exists (
      select 1 from public.factura_ingreso f
      where f.id_factura = detalle_factura.id_factura and f.id_sucursal = mi_id_suc()
    )
  );

alter table public.detalle_entrega enable row level security;
drop policy if exists propia_sede_detalle_entrega on public.detalle_entrega;
create policy propia_sede_detalle_entrega on public.detalle_entrega
  for all using (
    soy_admin() or exists (
      select 1 from public.entrega_insumo e
      where e.id_entrega = detalle_entrega.id_entrega and e.id_sucursal = mi_id_suc()
    )
  )
  with check (
    soy_admin() or exists (
      select 1 from public.entrega_insumo e
      where e.id_entrega = detalle_entrega.id_entrega and e.id_sucursal = mi_id_suc()
    )
  );

alter table public.colaborador_stock_dotacion enable row level security;
drop policy if exists propia_sede_dotacion on public.colaborador_stock_dotacion;
create policy propia_sede_dotacion on public.colaborador_stock_dotacion
  for all using (
    soy_admin() or exists (
      select 1 from public.colaborador c
      where c.id_colaborador = colaborador_stock_dotacion.id_colaborador and c.id_sucursal = mi_id_suc()
    )
  )
  with check (
    soy_admin() or exists (
      select 1 from public.colaborador c
      where c.id_colaborador = colaborador_stock_dotacion.id_colaborador and c.id_sucursal = mi_id_suc()
    )
  );

alter table public.anulacion_factura_detalle_revision enable row level security;
drop policy if exists propia_sede_anulacion_detalle on public.anulacion_factura_detalle_revision;
create policy propia_sede_anulacion_detalle on public.anulacion_factura_detalle_revision
  for all using (
    soy_admin() or exists (
      select 1 from public.anulacion_factura_solicitud a
      where a.id_solicitud = anulacion_factura_detalle_revision.id_solicitud and a.id_sucursal = mi_id_suc()
    )
  )
  with check (
    soy_admin() or exists (
      select 1 from public.anulacion_factura_solicitud a
      where a.id_solicitud = anulacion_factura_detalle_revision.id_solicitud and a.id_sucursal = mi_id_suc()
    )
  );

-- ---------------------------------------------------------------------
-- 6. Transferencias: visibles para origen Y destino (informacion
--    "compartida"), ademas de admin.
-- ---------------------------------------------------------------------
alter table public.salida_stock enable row level security;
drop policy if exists compartida_salida_stock on public.salida_stock;
create policy compartida_salida_stock on public.salida_stock
  for all using (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  )
  with check (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  );

alter table public.transferencia_producto enable row level security;
drop policy if exists compartida_transferencia_producto on public.transferencia_producto;
create policy compartida_transferencia_producto on public.transferencia_producto
  for all using (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  )
  with check (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  );

alter table public.transferencia_stock_solicitud enable row level security;
drop policy if exists compartida_transferencia_stock_solicitud on public.transferencia_stock_solicitud;
create policy compartida_transferencia_stock_solicitud on public.transferencia_stock_solicitud
  for all using (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  )
  with check (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  );

alter table public.transferencia_colaborador enable row level security;
drop policy if exists compartida_transferencia_colaborador on public.transferencia_colaborador;
create policy compartida_transferencia_colaborador on public.transferencia_colaborador
  for all using (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  )
  with check (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  );

alter table public.transferencia_colaborador_solicitud enable row level security;
drop policy if exists compartida_transferencia_colaborador_solicitud on public.transferencia_colaborador_solicitud;
create policy compartida_transferencia_colaborador_solicitud on public.transferencia_colaborador_solicitud
  for all using (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  )
  with check (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  );

alter table public.colaborador_movimiento enable row level security;
drop policy if exists compartida_colaborador_movimiento on public.colaborador_movimiento;
create policy compartida_colaborador_movimiento on public.colaborador_movimiento
  for all using (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  )
  with check (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  );

alter table public.transferencia_lote enable row level security;
drop policy if exists compartida_transferencia_lote on public.transferencia_lote;
create policy compartida_transferencia_lote on public.transferencia_lote
  for all using (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  )
  with check (
    id_sucursal_origen = mi_id_suc() or id_sucursal_destino = mi_id_suc() or soy_admin()
  );

alter table public.transferencia_lote_detalle enable row level security;
drop policy if exists compartida_transferencia_lote_detalle on public.transferencia_lote_detalle;
create policy compartida_transferencia_lote_detalle on public.transferencia_lote_detalle
  for all using (
    soy_admin() or exists (
      select 1 from public.transferencia_lote t
      where t.id_lote = transferencia_lote_detalle.id_lote
        and (t.id_sucursal_origen = mi_id_suc() or t.id_sucursal_destino = mi_id_suc())
    )
  )
  with check (
    soy_admin() or exists (
      select 1 from public.transferencia_lote t
      where t.id_lote = transferencia_lote_detalle.id_lote
        and (t.id_sucursal_origen = mi_id_suc() or t.id_sucursal_destino = mi_id_suc())
    )
  );

-- =====================================================================
-- Fin. Verificar con:
--   select tablename, rowsecurity from pg_tables
--   where schemaname = 'public' order by tablename;
-- (rowsecurity debe salir "true" en todas las tablas de arriba)
-- =====================================================================
