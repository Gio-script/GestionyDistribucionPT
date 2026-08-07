-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.producto_catalogo (
  id_producto integer NOT NULL DEFAULT nextval('producto_catalogo_id_producto_seq'::regclass),
  nombre_item character varying NOT NULL,
  categoria character varying NOT NULL,
  tipo_prenda character varying NOT NULL CHECK (tipo_prenda::text = ANY (ARRAY['Superior'::character varying::text, 'Inferior'::character varying::text, 'Calzado'::character varying::text, 'Accesorio'::character varying::text])),
  talla character varying NOT NULL DEFAULT 'UNICA'::character varying,
  precio_unitario numeric NOT NULL DEFAULT 0.00 CHECK (precio_unitario >= 0::numeric),
  tiene_variacion_genero boolean DEFAULT false,
  CONSTRAINT producto_catalogo_pkey PRIMARY KEY (id_producto)
);
CREATE TABLE public.colaborador (
  id_colaborador integer NOT NULL DEFAULT nextval('colaborador_id_colaborador_seq'::regclass),
  rut character varying NOT NULL UNIQUE,
  nombre character varying NOT NULL,
  apellido character varying NOT NULL,
  correo character varying,
  tipo_personal character varying NOT NULL CHECK (tipo_personal::text = ANY (ARRAY['Staff Normal'::character varying::text, 'Mantención'::character varying::text, 'Staff VIP'::character varying::text, 'Supervisor'::character varying::text])),
  talla_superior character varying NOT NULL,
  talla_inferior character varying NOT NULL,
  fecha_ingreso date NOT NULL,
  id_sucursal integer NOT NULL,
  activo boolean NOT NULL DEFAULT true,
  fecha_registro timestamp with time zone NOT NULL DEFAULT now(),
  talla_calzado character varying NOT NULL DEFAULT '0'::character varying,
  genero character varying DEFAULT 'no_responde'::character varying CHECK (genero::text = ANY (ARRAY['hombre'::character varying, 'mujer'::character varying, 'no_responde'::character varying]::text[])),
  CONSTRAINT colaborador_pkey PRIMARY KEY (id_colaborador),
  CONSTRAINT colaborador_id_sucursal_fkey FOREIGN KEY (id_sucursal) REFERENCES public.sucursal_usuaria(id_suc)
);
CREATE TABLE public.inventario_stock (
  id_stock integer NOT NULL DEFAULT nextval('inventario_stock_id_stock_seq'::regclass),
  id_sucursal integer NOT NULL,
  id_producto integer NOT NULL,
  talla character varying NOT NULL,
  cantidad_disponible integer NOT NULL DEFAULT 0 CHECK (cantidad_disponible >= 0),
  cantidad_merma integer NOT NULL DEFAULT 0 CHECK (cantidad_merma >= 0),
  genero character varying DEFAULT 'unisex'::character varying,
  CONSTRAINT inventario_stock_pkey PRIMARY KEY (id_stock),
  CONSTRAINT inventario_stock_id_producto_fkey FOREIGN KEY (id_producto) REFERENCES public.producto_catalogo(id_producto),
  CONSTRAINT inventario_stock_id_sucursal_fkey FOREIGN KEY (id_sucursal) REFERENCES public.sucursal_usuaria(id_suc)
);
CREATE TABLE public.salida_stock (
  id_salida integer NOT NULL DEFAULT nextval('salida_stock_id_salida_seq'::regclass),
  id_sucursal_origen integer NOT NULL,
  tipo_salida character varying NOT NULL CHECK (tipo_salida::text = ANY (ARRAY['Merma por desgaste'::character varying::text, 'Extravio'::character varying::text, 'Renuncia sin devolucion'::character varying::text, 'Transferencia'::character varying::text, 'Devolucion a proveedor'::character varying::text])),
  id_producto integer NOT NULL,
  talla character varying NOT NULL,
  cantidad integer NOT NULL CHECK (cantidad > 0),
  id_sucursal_destino integer,
  fecha_salida timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT salida_stock_pkey PRIMARY KEY (id_salida),
  CONSTRAINT salida_stock_id_producto_fkey FOREIGN KEY (id_producto) REFERENCES public.producto_catalogo(id_producto),
  CONSTRAINT salida_stock_id_sucursal_destino_fkey FOREIGN KEY (id_sucursal_destino) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT salida_stock_id_sucursal_origen_fkey FOREIGN KEY (id_sucursal_origen) REFERENCES public.sucursal_usuaria(id_suc)
);
CREATE TABLE public.factura_ingreso (
  id_factura integer NOT NULL DEFAULT nextval('factura_ingreso_id_factura_seq'::regclass),
  correlativo_factura integer NOT NULL,
  rut_proveedor character varying NOT NULL,
  nombre_proveedor character varying NOT NULL,
  fecha_ingreso timestamp with time zone NOT NULL DEFAULT now(),
  id_sucursal integer NOT NULL,
  id_usuario_registra uuid NOT NULL,
  CONSTRAINT factura_ingreso_pkey PRIMARY KEY (id_factura),
  CONSTRAINT factura_ingreso_id_sucursal_fkey FOREIGN KEY (id_sucursal) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT factura_ingreso_id_usuario_registra_fkey FOREIGN KEY (id_usuario_registra) REFERENCES public.sucursal_usuaria(id_usuario)
);
CREATE TABLE public.detalle_factura (
  id_detalle_factura integer NOT NULL DEFAULT nextval('detalle_factura_id_detalle_factura_seq'::regclass),
  id_factura integer NOT NULL,
  id_producto integer NOT NULL,
  talla character varying NOT NULL,
  cantidad integer NOT NULL CHECK (cantidad > 0),
  genero character varying,
  CONSTRAINT detalle_factura_pkey PRIMARY KEY (id_detalle_factura),
  CONSTRAINT detalle_factura_id_factura_fkey FOREIGN KEY (id_factura) REFERENCES public.factura_ingreso(id_factura),
  CONSTRAINT detalle_factura_id_producto_fkey FOREIGN KEY (id_producto) REFERENCES public.producto_catalogo(id_producto)
);
CREATE TABLE public.entrega_insumo (
  id_entrega integer NOT NULL DEFAULT nextval('entrega_insumo_id_entrega_seq'::regclass),
  id_colaborador integer NOT NULL,
  id_sucursal integer NOT NULL,
  id_usuario_despacha uuid NOT NULL,
  fecha_entrega timestamp with time zone NOT NULL DEFAULT now(),
  firma_digital_url text NOT NULL,
  CONSTRAINT entrega_insumo_pkey PRIMARY KEY (id_entrega),
  CONSTRAINT entrega_insumo_id_colaborador_fkey FOREIGN KEY (id_colaborador) REFERENCES public.colaborador(id_colaborador),
  CONSTRAINT entrega_insumo_id_sucursal_fkey FOREIGN KEY (id_sucursal) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT entrega_insumo_id_usuario_despacha_fkey FOREIGN KEY (id_usuario_despacha) REFERENCES public.sucursal_usuaria(id_usuario)
);
CREATE TABLE public.detalle_entrega (
  id_detalle_entrega integer NOT NULL DEFAULT nextval('detalle_entrega_id_detalle_entrega_seq'::regclass),
  id_entrega integer NOT NULL,
  id_producto integer NOT NULL,
  talla character varying NOT NULL,
  cantidad integer NOT NULL CHECK (cantidad > 0),
  genero character varying,
  CONSTRAINT detalle_entrega_pkey PRIMARY KEY (id_detalle_entrega),
  CONSTRAINT detalle_entrega_id_entrega_fkey FOREIGN KEY (id_entrega) REFERENCES public.entrega_insumo(id_entrega),
  CONSTRAINT detalle_entrega_id_producto_fkey FOREIGN KEY (id_producto) REFERENCES public.producto_catalogo(id_producto)
);
CREATE TABLE public.anulacion_factura_solicitud (
  id_solicitud integer NOT NULL DEFAULT nextval('anulacion_factura_solicitud_id_solicitud_seq'::regclass),
  id_factura integer NOT NULL,
  folio_factura integer NOT NULL,
  rut_proveedor character varying NOT NULL,
  nombre_proveedor character varying NOT NULL,
  fecha_solicitud timestamp with time zone NOT NULL DEFAULT now(),
  id_sucursal integer NOT NULL,
  id_usuario_solicita uuid NOT NULL,
  estado character varying NOT NULL DEFAULT 'PENDIENTE'::character varying CHECK (estado::text = ANY (ARRAY['PENDIENTE'::character varying::text, 'APROBADA'::character varying::text, 'RECHAZADA'::character varying::text, 'CANCELADA'::character varying::text])),
  motivo text,
  fecha_resolucion timestamp with time zone,
  id_usuario_resuelve uuid,
  observacion_resolucion text,
  CONSTRAINT anulacion_factura_solicitud_pkey PRIMARY KEY (id_solicitud),
  CONSTRAINT anulacion_factura_solicitud_id_factura_fkey FOREIGN KEY (id_factura) REFERENCES public.factura_ingreso(id_factura),
  CONSTRAINT anulacion_factura_solicitud_id_sucursal_fkey FOREIGN KEY (id_sucursal) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT anulacion_factura_solicitud_id_usuario_solicita_fkey FOREIGN KEY (id_usuario_solicita) REFERENCES public.sucursal_usuaria(id_usuario),
  CONSTRAINT anulacion_factura_solicitud_id_usuario_resuelve_fkey FOREIGN KEY (id_usuario_resuelve) REFERENCES public.sucursal_usuaria(id_usuario)
);
CREATE TABLE public.anulacion_factura_detalle_revision (
  id_revision integer NOT NULL DEFAULT nextval('anulacion_factura_detalle_revision_id_revision_seq'::regclass),
  id_solicitud integer NOT NULL,
  id_factura integer NOT NULL,
  id_producto integer NOT NULL,
  talla character varying NOT NULL,
  cantidad_revertida integer NOT NULL CHECK (cantidad_revertida > 0),
  fecha_application timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT anulacion_factura_detalle_revision_pkey PRIMARY KEY (id_revision),
  CONSTRAINT anulacion_factura_detalle_revision_id_solicitud_fkey FOREIGN KEY (id_solicitud) REFERENCES public.anulacion_factura_solicitud(id_solicitud),
  CONSTRAINT anulacion_factura_detalle_revision_id_factura_fkey FOREIGN KEY (id_factura) REFERENCES public.factura_ingreso(id_factura),
  CONSTRAINT anulacion_factura_detalle_revision_id_producto_fkey FOREIGN KEY (id_producto) REFERENCES public.producto_catalogo(id_producto)
);
CREATE TABLE public.sucursal_usuaria (
  id_suc integer NOT NULL DEFAULT nextval('sucursal_usuaria_id_suc_seq'::regclass),
  nombre_suc character varying,
  correo_usuario_suc character varying UNIQUE CHECK (correo_usuario_suc IS NULL OR correo_usuario_suc::text ~~ '%@cinepolis.com'::text),
  id_usuario uuid UNIQUE,
  estado boolean NOT NULL DEFAULT true,
  rol character varying NOT NULL DEFAULT 'usuario'::character varying CHECK (rol::text = ANY (ARRAY['admin'::character varying, 'usuario'::character varying]::text[])),
  CONSTRAINT sucursal_usuaria_pkey PRIMARY KEY (id_suc),
  CONSTRAINT sucursal_usuaria_id_usuario_fkey FOREIGN KEY (id_usuario) REFERENCES auth.users(id)
);
CREATE TABLE public.colaborador_stock_dotacion (
  id_colaborador_stock integer NOT NULL DEFAULT nextval('colaborador_stock_dotacion_id_colaborador_stock_seq'::regclass),
  id_colaborador integer NOT NULL,
  id_producto integer NOT NULL,
  talla character varying NOT NULL,
  cantidad_en_uso integer NOT NULL DEFAULT 0 CHECK (cantidad_en_uso >= 0),
  fecha_actualizacion timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT colaborador_stock_dotacion_pkey PRIMARY KEY (id_colaborador_stock),
  CONSTRAINT fk_colaborador FOREIGN KEY (id_colaborador) REFERENCES public.colaborador(id_colaborador),
  CONSTRAINT fk_producto FOREIGN KEY (id_producto) REFERENCES public.producto_catalogo(id_producto)
);
CREATE TABLE public.transferencia_colaborador (
  id_transferencia integer NOT NULL DEFAULT nextval('transferencia_colaborador_id_transferencia_seq'::regclass),
  id_colaborador integer NOT NULL,
  id_sucursal_origen integer NOT NULL,
  id_sucursal_destino integer NOT NULL,
  fecha_transferencia timestamp with time zone NOT NULL DEFAULT now(),
  id_usuario_transfiere uuid,
  observacion text,
  CONSTRAINT transferencia_colaborador_pkey PRIMARY KEY (id_transferencia),
  CONSTRAINT transferencia_colaborador_id_colaborador_fkey FOREIGN KEY (id_colaborador) REFERENCES public.colaborador(id_colaborador),
  CONSTRAINT transferencia_colaborador_id_sucursal_origen_fkey FOREIGN KEY (id_sucursal_origen) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT transferencia_colaborador_id_sucursal_destino_fkey FOREIGN KEY (id_sucursal_destino) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT transferencia_colaborador_id_usuario_transfiere_fkey FOREIGN KEY (id_usuario_transfiere) REFERENCES public.sucursal_usuaria(id_usuario)
);
CREATE TABLE public.transferencia_producto (
  id_trans_prod integer NOT NULL DEFAULT nextval('transferencia_producto_id_trans_prod_seq'::regclass),
  id_producto integer,
  id_sucursal_origen integer,
  id_sucursal_destino integer,
  cantidad integer,
  fecha_transferencia timestamp with time zone DEFAULT now(),
  CONSTRAINT transferencia_producto_pkey PRIMARY KEY (id_trans_prod),
  CONSTRAINT transferencia_producto_id_producto_fkey FOREIGN KEY (id_producto) REFERENCES public.producto_catalogo(id_producto),
  CONSTRAINT transferencia_producto_id_sucursal_origen_fkey FOREIGN KEY (id_sucursal_origen) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT transferencia_producto_id_sucursal_destino_fkey FOREIGN KEY (id_sucursal_destino) REFERENCES public.sucursal_usuaria(id_suc)
);
CREATE TABLE public.transferencia_stock_solicitud (
  id_solicitud bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  id_sucursal_origen bigint NOT NULL,
  id_sucursal_destino bigint NOT NULL,
  id_producto bigint NOT NULL,
  talla text NOT NULL,
  cantidad integer NOT NULL,
  motivo text,
  estado text NOT NULL DEFAULT 'PENDIENTE'::text,
  id_usuario_solicita uuid,
  id_usuario_resuelve uuid,
  fecha_solicitud timestamp with time zone DEFAULT now(),
  fecha_resolucion timestamp with time zone,
  observacion_resolucion text,
  CONSTRAINT transferencia_stock_solicitud_pkey PRIMARY KEY (id_solicitud),
  CONSTRAINT transferencia_stock_solicitud_id_sucursal_origen_fkey FOREIGN KEY (id_sucursal_origen) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT transferencia_stock_solicitud_id_sucursal_destino_fkey FOREIGN KEY (id_sucursal_destino) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT transferencia_stock_solicitud_id_producto_fkey FOREIGN KEY (id_producto) REFERENCES public.producto_catalogo(id_producto)
);
CREATE TABLE public.transferencia_colaborador_solicitud (
  id_solicitud bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  id_colaborador bigint NOT NULL,
  id_sucursal_origen bigint NOT NULL,
  id_sucursal_destino bigint NOT NULL,
  motivo text,
  estado text NOT NULL DEFAULT 'PENDIENTE'::text,
  id_usuario_solicita uuid,
  id_usuario_resuelve uuid,
  fecha_solicitud timestamp with time zone DEFAULT now(),
  fecha_resolucion timestamp with time zone,
  observacion_resolucion text,
  CONSTRAINT transferencia_colaborador_solicitud_pkey PRIMARY KEY (id_solicitud),
  CONSTRAINT transferencia_colaborador_solicitud_id_colaborador_fkey FOREIGN KEY (id_colaborador) REFERENCES public.colaborador(id_colaborador),
  CONSTRAINT transferencia_colaborador_solicitud_id_sucursal_origen_fkey FOREIGN KEY (id_sucursal_origen) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT transferencia_colaborador_solicitud_id_sucursal_destino_fkey FOREIGN KEY (id_sucursal_destino) REFERENCES public.sucursal_usuaria(id_suc)
);
CREATE TABLE public.colaborador_movimiento (
  id_movimiento integer NOT NULL DEFAULT nextval('colaborador_movimiento_id_movimiento_seq'::regclass),
  id_colaborador integer NOT NULL,
  id_sucursal_origen integer NOT NULL,
  id_sucursal_destino integer NOT NULL,
  motivo text,
  fecha_movimiento timestamp without time zone DEFAULT now(),
  id_usuario_autoriza uuid,
  CONSTRAINT colaborador_movimiento_pkey PRIMARY KEY (id_movimiento),
  CONSTRAINT colaborador_movimiento_id_colaborador_fkey FOREIGN KEY (id_colaborador) REFERENCES public.colaborador(id_colaborador),
  CONSTRAINT colaborador_movimiento_id_sucursal_origen_fkey FOREIGN KEY (id_sucursal_origen) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT colaborador_movimiento_id_sucursal_destino_fkey FOREIGN KEY (id_sucursal_destino) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT colaborador_movimiento_id_usuario_autoriza_fkey FOREIGN KEY (id_usuario_autoriza) REFERENCES public.sucursal_usuaria(id_usuario)
);
CREATE TABLE public.notificacion (
  id_notificacion integer NOT NULL DEFAULT nextval('notificacion_id_notificacion_seq'::regclass),
  id_sucursal integer,
  origen character varying DEFAULT 'superadmin'::character varying,
  titulo text NOT NULL,
  mensaje text NOT NULL,
  id_referencia integer,
  tipo_referencia character varying,
  leido boolean DEFAULT false,
  fecha_creacion timestamp without time zone DEFAULT now(),
  CONSTRAINT notificacion_pkey PRIMARY KEY (id_notificacion),
  CONSTRAINT notificacion_id_sucursal_fkey FOREIGN KEY (id_sucursal) REFERENCES public.sucursal_usuaria(id_suc)
);
CREATE TABLE public.csv_generados (
  id_csv integer NOT NULL DEFAULT nextval('csv_generados_id_csv_seq'::regclass),
  folio character varying NOT NULL UNIQUE,
  id_sucursal integer NOT NULL,
  id_usuario_genera uuid NOT NULL,
  fecha_generacion timestamp with time zone DEFAULT now(),
  fecha_expiracion timestamp with time zone NOT NULL,
  cantidad_registros integer NOT NULL,
  ruta_archivo text NOT NULL,
  estado character varying DEFAULT 'ACTIVO'::character varying CHECK (estado::text = ANY (ARRAY['ACTIVO'::character varying, 'EXPIRADO'::character varying, 'ELIMINADO'::character varying]::text[])),
  CONSTRAINT csv_generados_pkey PRIMARY KEY (id_csv),
  CONSTRAINT csv_generados_id_sucursal_fkey FOREIGN KEY (id_sucursal) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT csv_generados_id_usuario_fkey FOREIGN KEY (id_usuario_genera) REFERENCES public.sucursal_usuaria(id_usuario)
);
CREATE TABLE public.transferencia_lote (
  id_lote bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  id_sucursal_origen bigint NOT NULL,
  id_sucursal_destino bigint NOT NULL,
  id_usuario_envia uuid,
  id_usuario_recibe uuid,
  motivo text,
  estado text NOT NULL DEFAULT 'EN_TRANSITO'::text CHECK (estado = ANY (ARRAY['EN_TRANSITO'::text, 'RECIBIDO'::text, 'RECHAZADO'::text])),
  fecha_envio timestamp with time zone NOT NULL DEFAULT now(),
  fecha_resolucion timestamp with time zone,
  observacion_resolucion text,
  CONSTRAINT transferencia_lote_pkey PRIMARY KEY (id_lote),
  CONSTRAINT transferencia_lote_id_sucursal_origen_fkey FOREIGN KEY (id_sucursal_origen) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT transferencia_lote_id_sucursal_destino_fkey FOREIGN KEY (id_sucursal_destino) REFERENCES public.sucursal_usuaria(id_suc),
  CONSTRAINT transferencia_lote_id_usuario_envia_fkey FOREIGN KEY (id_usuario_envia) REFERENCES public.sucursal_usuaria(id_usuario),
  CONSTRAINT transferencia_lote_id_usuario_recibe_fkey FOREIGN KEY (id_usuario_recibe) REFERENCES public.sucursal_usuaria(id_usuario)
);
CREATE TABLE public.transferencia_lote_detalle (
  id_detalle bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  id_lote bigint NOT NULL,
  id_producto integer NOT NULL,
  talla character varying NOT NULL,
  cantidad integer NOT NULL CHECK (cantidad > 0),
  CONSTRAINT transferencia_lote_detalle_pkey PRIMARY KEY (id_detalle),
  CONSTRAINT transferencia_lote_detalle_id_lote_fkey FOREIGN KEY (id_lote) REFERENCES public.transferencia_lote(id_lote),
  CONSTRAINT transferencia_lote_detalle_id_producto_fkey FOREIGN KEY (id_producto) REFERENCES public.producto_catalogo(id_producto)
);