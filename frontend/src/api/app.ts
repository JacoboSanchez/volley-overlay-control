/** Deployment-wide app configuration — ``/api/v1/app-config``. */

import type { components } from './schema';
import { request } from './http';

export type AppConfig = components['schemas']['AppConfigResponse'];

export function getAppConfig(): Promise<AppConfig> {
  return request<AppConfig>('GET', '/app-config');
}
