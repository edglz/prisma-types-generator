# Prisma TypeTags (Prisma → TypeScript GUI)

Herramienta de escritorio (Tkinter) para convertir un esquema Prisma (`schema.prisma`) en tipos de TypeScript. Prisma TypeTags genera un único archivo o divide por esquemas, con opciones como tipos "planos" y un `index.ts` de reexportación.

## Características

- **Interfaz gráfica** simple con carga de `schema.prisma` y vista previa en vivo.
- **Generación en un archivo** (`models.ts`) o **dividido por schema** en múltiples archivos.
- Opción de **tipos planos** (`*Flat`) que omiten relaciones.
- Opción para generar **`index.ts`** que reexporta los módulos generados.
- Sin dependencias externas: usa solo la **biblioteca estándar de Python**.

## Requisitos

- Python 3.10+ (probado con la biblioteca estándar: `tkinter`, `dataclasses`, `zipfile`).
- Sistema operativo con soporte para `tkinter` (Windows, macOS o Linux con entorno gráfico).

## Instalación

No se requieren paquetes adicionales.

1. Clona o descarga este repositorio.
2. (Opcional) Crea un entorno virtual.
3. Verifica que puedas abrir aplicaciones gráficas en tu sistema.

El archivo `requirements.txt` es meramente informativo (no hay dependencias de terceros).

## Uso rápido

1. Ejecuta la aplicación:

```bash
python main.py
```

2. En la ventana:
- **Cargar schema.prisma**: selecciona tu archivo Prisma.
- **Generar TypeScript**: procesa el esquema y muestra la vista previa.
- Opciones:
  - **Dividir por schema**: si usas directiva `@@schema("<nombre>")` en modelos, agrupa modelos por schema y genera un archivo `models.ts` por cada uno.
  - **Tipos planos**: agrega interfaces `NombreModeloFlat` con campos escalares/enums sin relaciones.
  - **Generar index.ts**: crea un índice con reexports de todos los archivos.
- **Guardar archivo actual**: exporta el archivo actualmente visible en la vista previa.
- **Guardar ZIP**: exporta todos los archivos generados como un `.zip` listo para usar.

## Salida generada

- **Modo archivo único** (por defecto):
  - `models.ts`: contiene tipos base, enums y todos los modelos.
  - Si marcas "Generar index.ts": añade `index.ts` que reexporta desde `./models`.

- **Modo dividido por schema**:
  - `common/base.ts`: tipos utilitarios (`DateTimeString`, `JsonValue`).
  - `common/enums.ts`: definición de todos los `enum`.
  - `default/models.ts`, `mi_schema/models.ts`, etc.: interfaces para cada schema.
  - (Opcional) `index.ts`: reexports de `common/` y cada `<schema>/models`.

La herramienta resuelve importaciones entre schemas cuando un modelo referencia a otro modelo ubicado en un schema distinto.

## Reglas de mapeo Prisma → TypeScript

- Escalares:
  - `String` → `string`
  - `Int`, `Float`, `Decimal`, `BigInt` → `number`
  - `Boolean` → `boolean`
  - `DateTime` → `DateTimeString` (alias `string`)
  - `Json` → `JsonValue` (alias `any`)
- Enums Prisma → union de literales de cadena (ej: `"A" | "B"`).
- Relaciones a otros modelos → `Model | null` (o `Model[] | null` si es lista).
- Escalares/enums opcionales → `Tipo | null`.
- Tipos de lista escalares/enums → `Tipo[]` (si opcional: `Tipo[] | null`).
- Tipos planos (`*Flat`) omiten campos relacionales y mantienen solo escalares/enums.

## Ejemplo mínimo

Entrada Prisma:

```prisma
enum Role {
  USER
  ADMIN
}

model User {
  id        Int      @id @default(autoincrement())
  email     String   @unique
  role      Role
  posts     Post[]
}

model Post {
  id        Int      @id @default(autoincrement())
  title     String
  author    User?
}
```

Salida (fragmento `models.ts`, modo simple):

```ts
export type DateTimeString = string;
export type JsonValue = any;

export type Role = "USER" | "ADMIN";

export interface User {}
export interface Post {}

export interface User {
  id: number;
  email: string;
  role: Role;
  posts: Post[] | null;
}

export interface Post {
  id: number;
  title: string;
  author: User | null;
}
```

## Limitaciones actuales

- Parser básico: ignora comentarios en línea (`//`), directivas de campo/índice salvo `@@schema("...")` en modelos.
- No procesa validaciones complejas, atributos específicos (ej. `@default`, `@relation`), ni claves compuestas para modificar los tipos.
- `JsonValue` se mapea a `any`; puedes ajustarlo en `common/base.ts` si prefieres una definición más estricta.
- `Decimal`/`BigInt` se mapean a `number` por simplicidad.

## Roadmap sugerido

- Soporte de más directivas Prisma para enriquecer tipos generados (nullable, default, unique, relaciones avanzadas).
- Hooks o plantillas para personalizar la salida (nombres, prefijos/sufijos, paths).
- CLI adicional (modo no-UI) para integraciones en pipelines.
- Tipos más estrictos para `Json` y `Decimal` (ej. branded types).
- Tests unitarios y de snapshot sobre esquemas de ejemplo.

## Desarrollo

- Código principal en `main.py`.
- No hay dependencias externas; si añades nuevas, recuerda actualizar `requirements.txt`.

### Ejecutar en desarrollo

```bash
python main.py
```

### Estructura (cuando se genera dividido por schema)

```
common/
  base.ts
  enums.ts
<schema>/
  models.ts
index.ts (opcional)
```

## Contribuciones

¡Las PRs y sugerencias son bienvenidas! Por favor, abre un issue para discutir cambios mayores.

## Licencia

Este proyecto está licenciado bajo la **MIT License**. Puedes usarlo comercialmente siempre que mantengas la atribución. Consulta el archivo `LICENSE` para más detalles.
