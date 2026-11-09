import type { CatalogItem } from "@/lib/types";

export function CatalogForm({ item, published, error }: { item?: CatalogItem; published?: boolean; error?: string }) {
  const install = item?.install;
  return (
    <form className="form" action="/api/mgmt/catalog" method="post">
      {error ? <p className="banner banner-warn" role="alert">{error}</p> : null}
      <label className="field"><span>Id</span><input name="id" defaultValue={item?.id ?? ""} required readOnly={Boolean(item)} /></label>
      <label className="field"><span>Name</span><input name="name" defaultValue={item?.name ?? ""} required /></label>
      <label className="field"><span>Summary</span><input name="summary" defaultValue={item?.summary ?? ""} required maxLength={160} /></label>
      <label className="field"><span>Description</span><textarea name="description" defaultValue={item?.description ?? ""} required /></label>
      <label className="field"><span>Version</span><input name="version" defaultValue={item?.version ?? ""} required /></label>
      <label className="field"><span>Category</span><input name="category" defaultValue={item?.category ?? ""} required /></label>
      <label className="field"><span>Publisher</span><input name="publisher" defaultValue={item?.publisher ?? ""} required /></label>
      <label className="field"><span>Homepage</span><input name="homepage" defaultValue={item?.homepage ?? ""} required /></label>
      <label className="field"><span>License</span><input name="license" defaultValue={item?.license ?? ""} required /></label>
      <label className="field"><span>Minimum OS version</span><input name="min_os_version" defaultValue={item?.min_os_version ?? "0.1.0"} required /></label>
      <label className="field">
        <span>Install method</span>
        <select name="method" defaultValue={install?.method ?? "apt"}>
          <option value="apt">apt</option>
          <option value="flatpak">flatpak</option>
          <option value="deb">deb</option>
          <option value="script">script</option>
        </select>
      </label>
      <label className="field"><span>apt package</span><input name="package" defaultValue={install?.package ?? ""} /></label>
      <label className="field"><span>Flatpak id</span><input name="flatpak_id" defaultValue={install?.flatpak_id ?? ""} /></label>
      <label className="field"><span>deb or script URL</span><input name="url" defaultValue={install?.url ?? ""} /></label>
      <label className="field"><span>deb or script SHA-256</span><input name="artifact_sha256" defaultValue={install?.sha256 ?? ""} className="mono" /></label>
      <label className="field"><span>Icon URL</span><input name="icon_url" defaultValue={item?.icon.url ?? ""} required /></label>
      <label className="field"><span>Icon SHA-256</span><input name="icon_sha256" defaultValue={item?.icon.sha256 ?? ""} required className="mono" /></label>
      <label className="check"><input type="checkbox" name="example" defaultChecked={item?.example === true} /> Example item</label>
      <label className="check"><input type="checkbox" name="published" defaultChecked={published === true} /> Published in the signed catalog</label>
      <button className="button" type="submit">Save</button>
    </form>
  );
}
