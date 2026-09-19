import assert from "node:assert/strict";
import test from "node:test";

import {
  decryptCredential,
  encryptCredential,
  parseEncryptedCredential,
} from "../lib/credential-vault.ts";

const masterKey = Buffer.alloc(32, 7).toString("base64");

test("credential vault encrypts without retaining plaintext and decrypts with the same key", async () => {
  const secret = "comtrade-primary-key-example";
  const encrypted = await encryptCredential(secret, masterKey);
  const serialized = JSON.stringify(encrypted);

  assert.equal(serialized.includes(secret), false);
  assert.equal(await decryptCredential(parseEncryptedCredential(serialized), masterKey), secret);
});

test("credential vault rejects a different master key", async () => {
  const encrypted = await encryptCredential("private-value", masterKey);
  const differentKey = Buffer.alloc(32, 9).toString("base64");

  await assert.rejects(() => decryptCredential(encrypted, differentKey));
});

test("credential vault requires a 256-bit master key", async () => {
  await assert.rejects(
    () => encryptCredential("private-value", Buffer.alloc(16).toString("base64")),
    /密钥保险箱尚未初始化/,
  );
});
