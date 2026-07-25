{ callPackage, withHardening ? false, withExtraHardening ? false, ... }@args:

callPackage ./generic.nix
(args // { inherit withHardening withExtraHardening; }) {
  version = "1.28.0";
  hash = "sha256-xrXGsIbA3508o/9eCEwdDvkJ5gOCecccHD6YX1dv92o=";
}
