import { fromBase64, toBase64 } from '@atcute/multibase';

export interface Bytes {
	$bytes: string;
}

export class BytesWrapper implements Bytes {
	constructor(public buf: Uint8Array) {}

	get $bytes(): string {
		return toBase64(this.buf);
	}

	toJSON(): Bytes {
		return { $bytes: this.$bytes };
	}
}

export const toBytes = (buf: Uint8Array): Bytes => {
	return new BytesWrapper(buf);
};

export const fromBytes = (bytes: Bytes): Uint8Array => {
	if (bytes instanceof BytesWrapper) {
		return bytes.buf;
	}

	return fromBase64(bytes.$bytes);
};
