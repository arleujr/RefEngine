import type { components } from './schema';

export type Health = components['schemas']['HealthResponse'];
export type InputInventory = components['schemas']['InputInventoryResponse'];
export type Run = components['schemas']['RunResponse'];
export type WorkSummary = components['schemas']['WorkSummaryResponse'];
export type WorkDetail = components['schemas']['WorkDetailResponse'];
export type WorkAction = components['schemas']['WorkActionResponse'];
export type PublishResponse = components['schemas']['PublishResponse'];
export type SchemaDefinition = components['schemas']['SchemaResponse'];
export type CatalogField = components['schemas']['CatalogFieldResponse'];
export type WorkPatch = components['schemas']['WorkPatchRequest'];
export interface ApiErrorPayload {
  error: string;
  message: string;
  details?: Record<string, unknown>;
}
