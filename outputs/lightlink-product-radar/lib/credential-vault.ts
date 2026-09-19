const CREDENTIAL_AAD = new TextEncoder().encode("lightlink-credential-v1");

export type EncryptedCredential = {
  version: 1;
  algorithm: "AES-GCM";
  iv: string;
  ciphertext: string;
};

function bytesToBase64(bytes: Uint8Array) {
  let value = "";
  for (const byte of bytes) value += String.fromCharCode(byte);
  return btoa(value);
}

function base64ToBytes(value: string) {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function importMasterKey(masterKey: string) {
  const bytes = base64ToBytes(masterKey.trim());
  if (bytes.byteLength !== 32) {
    throw new Error("本机密钥保险箱尚未初始化，请重新启动 LightLink");
  }
  return crypto.subtle.importKey("raw", bytes, "AES-GCM", false, ["encrypt", "decrypt"]);
}

export async function encryptCredential(secret: string, masterKey: string): Promise<EncryptedCredential> {
  const normalized = secret.trim();
  if (!normalized) throw new Error("API Key 不能为空");
  const key = await importMasterKey(masterKey);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: CREDENTIAL_AAD },
    key,
    new TextEncoder().encode(normalized),
  );
  return {
    version: 1,
    algorithm: "AES-GCM",
    iv: bytesToBase64(iv),
    ciphertext: bytesToBase64(new Uint8Array(ciphertext)),
  };
}

export async function decryptCredential(payload: EncryptedCredential, masterKey: string) {
  if (payload.version !== 1 || payload.algorithm !== "AES-GCM") {
    throw new Error("无法识别已保存的 API Key 格式");
  }
  const key = await importMasterKey(masterKey);
  const plaintext = await crypto.subtle.decrypt(
    {
      name: "AES-GCM",
      iv: base64ToBytes(payload.iv),
      additionalData: CREDENTIAL_AAD,
    },
    key,
    base64ToBytes(payload.ciphertext),
  );
  return new TextDecoder().decode(plaintext);
}

export function parseEncryptedCredential(value: string): EncryptedCredential {
  const payload = JSON.parse(value) as Partial<EncryptedCredential>;
  if (
    payload.version !== 1
    || payload.algorithm !== "AES-GCM"
    || typeof payload.iv !== "string"
    || typeof payload.ciphertext !== "string"
  ) {
    throw new Error("无法识别已保存的 API Key 格式");
  }
  return payload as EncryptedCredential;
}
