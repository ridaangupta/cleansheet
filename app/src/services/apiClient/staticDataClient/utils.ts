import { LOCAL_MEDIA_SERVER, MEDIA_SERVER } from '@AppSrc/cleansheet/config';
import { findById } from '@AppUtils/array';
import type { ApiResponse } from '../types';
import { buildResponse } from '../utils';
import type { StaticDataRequest } from './types';

export const performRequest = async <ResponseData>({
  endpoint,
  extras,
}: StaticDataRequest<ResponseData>): Promise<ApiResponse<ResponseData>> => {
  try {
    const timestampStart = performance.now();
    const responseData = withMediaServer(extras?.staticData?.[endpoint]);
    const timestampEnd = performance.now();
    const duration = timestampEnd - timestampStart;

    const response = responseData ? { status: 200 } : { status: 400 };

    try {
      const finalResponse = buildResponse(
        response,
        parseResponseData(responseData, extras?.id),
        {
          duration,
        },
      ) as ApiResponse<ResponseData>;

      return await Promise.resolve(finalResponse);
    } catch (error) {
      // TODO: handle error here
      // parsing response error
    }
  } catch (error) {
    // TODO: handle error here
    //sending request error
  }
  throw new Error('Perform a request failed');
};

const parseResponseData = <ResponseData>(
  responseData: ResponseData,
  id?: string,
): ResponseData => {
  if (Array.isArray(responseData) && id) {
    return findById(id, responseData);
  }

  return responseData;
};

/**
 * Cleansheet: the static catalogue JSON points its images at the dev Mac's mock server
 * (pipeline/ui_art.py); serve them from the configured media server (CloudFront) instead.
 */
const withMediaServer = <T>(data: T): T =>
  data === undefined || MEDIA_SERVER === LOCAL_MEDIA_SERVER
    ? data
    : (JSON.parse(
        JSON.stringify(data).split(LOCAL_MEDIA_SERVER).join(MEDIA_SERVER),
      ) as T);
