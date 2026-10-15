import { ApiError, getActiveOrgId } from "@/lib/api";

/**
 * Multipart upload with progress. `fetch` can't report upload progress, so this uses XMLHttpRequest with the same
 * conventions as `api()`: same-origin cookie, CSRF header, active org header, error envelope → ApiError.
 */
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress: (fraction: number) => void,
): { promise: Promise<T>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<T>((resolve, reject) => {
    xhr.open("POST", path);
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-Requested-With", "abos");
    const org = getActiveOrgId();
    if (org) xhr.setRequestHeader("X-Org-Id", org);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, "network_error", "Upload failed: cannot reach the server."));
    xhr.onabort = () => reject(new ApiError(0, "aborted", "Upload cancelled."));
    xhr.onload = () => {
      let body: { error?: { code: string; message: string; details?: unknown } } | null = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON (e.g. proxy error page) */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      else
        reject(new ApiError(xhr.status, body?.error?.code ?? "http_error",
          body?.error?.message ?? `Upload failed (${xhr.status})`, body?.error?.details));
    };
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}
