// Package types provides shared types and structs.
package types

// CertPair is a struct to hold a certificate and private key pair.
type CertPair struct {
	Certificate string `json:"certificate" yaml:"certificate"`
	PrivateKey  string `json:"private-key" yaml:"private-key"`
}
