-- Distribución de indumentaria por Superadmin: lotes de transferencia con confirmación
-- de recepción en destino. Ejecutar en el SQL Editor de Supabase.

CREATE TABLE public.transferencia_lote (
  id_lote bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_sucursal_origen bigint NOT NULL REFERENCES public.sucursal_usuaria(id_suc),
  id_sucursal_destino bigint NOT NULL REFERENCES public.sucursal_usuaria(id_suc),
  id_usuario_envia uuid REFERENCES public.sucursal_usuaria(id_usuario),
  id_usuario_recibe uuid REFERENCES public.sucursal_usuaria(id_usuario),
  motivo text,
  estado text NOT NULL DEFAULT 'EN_TRANSITO'
    CHECK (estado = ANY (ARRAY['EN_TRANSITO', 'RECIBIDO', 'RECHAZADO'])),
  fecha_envio timestamp with time zone NOT NULL DEFAULT now(),
  fecha_resolucion timestamp with time zone,
  observacion_resolucion text
);

CREATE TABLE public.transferencia_lote_detalle (
  id_detalle bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id_lote bigint NOT NULL REFERENCES public.transferencia_lote(id_lote),
  id_producto integer NOT NULL REFERENCES public.producto_catalogo(id_producto),
  talla character varying NOT NULL,
  cantidad integer NOT NULL CHECK (cantidad > 0)
);

-- El resto de las tablas del proyecto no usa RLS (todo el acceso pasa por el
-- backend FastAPI con la service_role key), así que estas dos quedan iguales.
ALTER TABLE public.transferencia_lote DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.transferencia_lote_detalle DISABLE ROW LEVEL SECURITY;
