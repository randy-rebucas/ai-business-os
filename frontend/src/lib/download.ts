import { ApiError, getActiveOrgId } from "@/lib/api";

/** Downloads need the X-Org-Id header, so fetch the file and save it rather than using a plain link. */
export async function downloadFile(path: string, fallbackName: string) {
  const res = await fetch(path, {
    headers: { "X-Org-Id": getActiveOrgId() ?? "", "X-Requested-With": "abos" }, credentials: "same-origin",
  });
  if (!res.ok) throw new ApiError(res.status, "download_failed", "Download failed");
  const name = decodeURIComponent(/filename\*=UTF-8''([^;]+)/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}
