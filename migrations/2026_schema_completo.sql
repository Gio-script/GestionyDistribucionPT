-- =====================================================================
-- Esquema completo para el proyecto Supabase nuevo (GestionyDistribucionPT)
-- =====================================================================
-- A diferencia de schema.sql (que es solo de referencia y NO respeta el
-- orden de dependencias), este script SI esta ordenado correctamente
-- para poder ejecutarse tal cual, de una sola pasada.
--
-- Como aplicar: Supabase Dashboard (proyecto NUEVO, amzluastalwzsompnqto)
-- -> SQL Editor -> pegar todo -> Run.
-- Solo crea estructura (tablas, PKs, FKs, checks) - SIN datos, ya que es
-- un proyecto personal y no corresponde llevarse datos reales de personas.
-- =====================================================================

-- 1. Sin dependencias
create table public.producto_catalogo (
  id_producto integer generated always as identity primary key,
  nombre_item character varying not null,
  categoria character varying not null,
  tipo_prenda character varying not null check (tipo_prenda = any (array['Superior','Inferior','Calzado','Accesorio'])),
  talla character varying not null default 'UNICA',
  precio_unitario numeric not null default 0.00 check (precio_unitario >= 0),
  tiene_variacion_genero boolean default false
);

-- 2. Depende de auth.users (integrado en cualquier proyecto Supabase)
create table public.sucursal_usuaria (
  id_suc integer generated always as identity primary key,
  nombre_suc character varying,
  correo_usuario_suc character varying unique check (correo_usuario_suc is null or correo_usuario_suc ~~ '%@%'),
  id_usuario uuid unique references auth.users(id),
  estado boolean not null default true,
  rol character varying not null default 'usuario' check (rol = any (array['admin','usuario']))
);

-- 3. Depende de sucursal_usuaria
create table public.colaborador (
  id_colaborador integer generated always as identity primary key,
  rut character varying not null unique,
  nombre character varying not null,
  apellido character varying not null,
  correo character varying,
  tipo_personal character varying not null check (tipo_personal = any (array['Staff Normal','Mantención','Staff VIP','Supervisor'])),
  talla_superior character varying not null,
  talla_inferior character varying not null,
  fecha_ingreso date not null,
  id_sucursal integer not null references public.sucursal_usuaria(id_suc),
  activo boolean not null default true,
  fecha_registro timestamp with time zone not null default now(),
  talla_calzado character varying not null default '0',
  genero character varying default 'no_responde' check (genero = any (array['hombre','mujer','no_responde']))
);

-- 4. Depende de producto_catalogo + sucursal_usuaria
create table public.inventario_stock (
  id_stock integer generated always as identity primary key,
  id_sucursal integer not null references public.sucursal_usuaria(id_suc),
  id_producto integer not null references public.producto_catalogo(id_producto),
  talla character varying not null,
  cantidad_disponible integer not null default 0 check (cantidad_disponible >= 0),
  cantidad_merma integer not null default 0 check (cantidad_merma >= 0),
  genero character varying default 'unisex'
);

create table public.salida_stock (
  id_salida integer generated always as identity primary key,
  id_sucursal_origen integer not null references public.sucursal_usuaria(id_suc),
  tipo_salida character varying not null check (tipo_salida = any (array['Merma por desgaste','Extravio','Renuncia sin devolucion','Transferencia','Devolucion a proveedor'])),
  id_producto integer not null references public.producto_catalogo(id_producto),
  talla character varying not null,
  cantidad integer not null check (cantidad > 0),
  id_sucursal_destino integer references public.sucursal_usuaria(id_suc),
  fecha_salida timestamp with time zone not null default now()
);

create table public.factura_ingreso (
  id_factura integer generated always as identity primary key,
  correlativo_factura integer not null,
  rut_proveedor character varying not null,
  nombre_proveedor character varying not null,
  fecha_ingreso timestamp with time zone not null default now(),
  id_sucursal integer not null references public.sucursal_usuaria(id_suc),
  id_usuario_registra uuid not null references public.sucursal_usuaria(id_usuario)
);

create table public.detalle_factura (
  id_detalle_factura integer generated always as identity primary key,
  id_factura integer not null references public.factura_ingreso(id_factura),
  id_producto integer not null references public.producto_catalogo(id_producto),
  talla character varying not null,
  cantidad integer not null check (cantidad > 0),
  genero character varying
);

create table public.entrega_insumo (
  id_entrega integer generated always as identity primary key,
  id_colaborador integer not null references public.colaborador(id_colaborador),
  id_sucursal integer not null references public.sucursal_usuaria(id_suc),
  id_usuario_despacha uuid not null references public.sucursal_usuaria(id_usuario),
  fecha_entrega timestamp with time zone not null default now(),
  firma_digital_url text not null
);

create table public.detalle_entrega (
  id_detalle_entrega integer generated always as identity primary key,
  id_entrega integer not null references public.entrega_insumo(id_entrega),
  id_producto integer not null references public.producto_catalogo(id_producto),
  talla character varying not null,
  cantidad integer not null check (cantidad > 0),
  genero character varying
);

create table public.anulacion_factura_solicitud (
  id_solicitud integer generated always as identity primary key,
  id_factura integer not null references public.factura_ingreso(id_factura),
  folio_factura integer not null,
  rut_proveedor character varying not null,
  nombre_proveedor character varying not null,
  fecha_solicitud timestamp with time zone not null default now(),
  id_sucursal integer not null references public.sucursal_usuaria(id_suc),
  id_usuario_solicita uuid not null references public.sucursal_usuaria(id_usuario),
  estado character varying not null default 'PENDIENTE' check (estado = any (array['PENDIENTE','APROBADA','RECHAZADA','CANCELADA'])),
  motivo text,
  fecha_resolucion timestamp with time zone,
  id_usuario_resuelve uuid references public.sucursal_usuaria(id_usuario),
  observacion_resolucion text
);

create table public.anulacion_factura_detalle_revision (
  id_revision integer generated always as identity primary key,
  id_solicitud integer not null references public.anulacion_factura_solicitud(id_solicitud),
  id_factura integer not null references public.factura_ingreso(id_factura),
  id_producto integer not null references public.producto_catalogo(id_producto),
  talla character varying not null,
  cantidad_revertida integer not null check (cantidad_revertida > 0),
  fecha_application timestamp with time zone not null default now()
);

create table public.colaborador_stock_dotacion (
  id_colaborador_stock integer generated always as identity primary key,
  id_colaborador integer not null references public.colaborador(id_colaborador),
  id_producto integer not null references public.producto_catalogo(id_producto),
  talla character varying not null,
  cantidad_en_uso integer not null default 0 check (cantidad_en_uso >= 0),
  fecha_actualizacion timestamp with time zone not null default now()
);

create table public.transferencia_colaborador (
  id_transferencia integer generated always as identity primary key,
  id_colaborador integer not null references public.colaborador(id_colaborador),
  id_sucursal_origen integer not null references public.sucursal_usuaria(id_suc),
  id_sucursal_destino integer not null references public.sucursal_usuaria(id_suc),
  fecha_transferencia timestamp with time zone not null default now(),
  id_usuario_transfiere uuid references public.sucursal_usuaria(id_usuario),
  observacion text
);

create table public.transferencia_producto (
  id_trans_prod integer generated always as identity primary key,
  id_producto integer references public.producto_catalogo(id_producto),
  id_sucursal_origen integer references public.sucursal_usuaria(id_suc),
  id_sucursal_destino integer references public.sucursal_usuaria(id_suc),
  cantidad integer,
  fecha_transferencia timestamp with time zone default now()
);

create table public.transferencia_stock_solicitud (
  id_solicitud bigint generated always as identity primary key,
  id_sucursal_origen bigint not null references public.sucursal_usuaria(id_suc),
  id_sucursal_destino bigint not null references public.sucursal_usuaria(id_suc),
  id_producto bigint not null references public.producto_catalogo(id_producto),
  talla text not null,
  cantidad integer not null,
  motivo text,
  estado text not null default 'PENDIENTE',
  id_usuario_solicita uuid,
  id_usuario_resuelve uuid,
  fecha_solicitud timestamp with time zone default now(),
  fecha_resolucion timestamp with time zone,
  observacion_resolucion text
);

create table public.transferencia_colaborador_solicitud (
  id_solicitud bigint generated always as identity primary key,
  id_colaborador bigint not null references public.colaborador(id_colaborador),
  id_sucursal_origen bigint not null references public.sucursal_usuaria(id_suc),
  id_sucursal_destino bigint not null references public.sucursal_usuaria(id_suc),
  motivo text,
  estado text not null default 'PENDIENTE',
  id_usuario_solicita uuid,
  id_usuario_resuelve uuid,
  fecha_solicitud timestamp with time zone default now(),
  fecha_resolucion timestamp with time zone,
  observacion_resolucion text
);

create table public.colaborador_movimiento (
  id_movimiento integer generated always as identity primary key,
  id_colaborador integer not null references public.colaborador(id_colaborador),
  id_sucursal_origen integer not null references public.sucursal_usuaria(id_suc),
  id_sucursal_destino integer not null references public.sucursal_usuaria(id_suc),
  motivo text,
  fecha_movimiento timestamp without time zone default now(),
  id_usuario_autoriza uuid references public.sucursal_usuaria(id_usuario)
);

create table public.notificacion (
  id_notificacion integer generated always as identity primary key,
  id_sucursal integer references public.sucursal_usuaria(id_suc),
  origen character varying default 'superadmin',
  titulo text not null,
  mensaje text not null,
  id_referencia integer,
  tipo_referencia character varying,
  leido boolean default false,
  fecha_creacion timestamp without time zone default now()
);

create table public.csv_generados (
  id_csv integer generated always as identity primary key,
  folio character varying not null unique,
  id_sucursal integer not null references public.sucursal_usuaria(id_suc),
  id_usuario_genera uuid not null references public.sucursal_usuaria(id_usuario),
  fecha_generacion timestamp with time zone default now(),
  fecha_expiracion timestamp with time zone not null,
  cantidad_registros integer not null,
  ruta_archivo text not null,
  estado character varying default 'ACTIVO' check (estado = any (array['ACTIVO','EXPIRADO','ELIMINADO']))
);

create table public.transferencia_lote (
  id_lote bigint generated always as identity primary key,
  id_sucursal_origen bigint not null references public.sucursal_usuaria(id_suc),
  id_sucursal_destino bigint not null references public.sucursal_usuaria(id_suc),
  id_usuario_envia uuid references public.sucursal_usuaria(id_usuario),
  id_usuario_recibe uuid references public.sucursal_usuaria(id_usuario),
  motivo text,
  estado text not null default 'EN_TRANSITO' check (estado = any (array['EN_TRANSITO','RECIBIDO','RECHAZADO'])),
  fecha_envio timestamp with time zone not null default now(),
  fecha_resolucion timestamp with time zone,
  observacion_resolucion text
);

create table public.transferencia_lote_detalle (
  id_detalle bigint generated always as identity primary key,
  id_lote bigint not null references public.transferencia_lote(id_lote),
  id_producto integer not null references public.producto_catalogo(id_producto),
  talla character varying not null,
  cantidad integer not null check (cantidad > 0)
);

-- =====================================================================
-- Fin. Verificar con:
--   select table_name from information_schema.tables
--   where table_schema = 'public' order by table_name;
-- (deberian salir 20 tablas)
-- =====================================================================
